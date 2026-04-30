const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const projectRoot = process.argv[2];
const outputFile = process.argv[3];

if (!projectRoot || !outputFile) {
  console.error('Usage: node ua-project-scan.js <projectRoot> <outputFile>');
  process.exit(1);
}

// Step 1: File Discovery
function discoverFiles(root) {
  try {
    const result = execSync('git ls-files', { cwd: root, encoding: 'utf-8' });
    return result.split('\n').filter(f => f.trim() !== '');
  } catch (e) {
    // Not a git repo, use recursive listing
    const files = [];
    function walk(dir) {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          walk(fullPath);
        } else {
          files.push(path.relative(root, fullPath).replace(/\\/g, '/'));
        }
      }
    }
    walk(root);
    return files;
  }
}

// Step 2: Exclusion filtering
function shouldExclude(filePath) {
  const normalized = filePath.replace(/\\/g, '/');

  // Dependency directories
  if (normalized.includes('node_modules/') || normalized.includes('.git/') ||
      normalized.includes('vendor/') || normalized.includes('venv/') ||
      normalized.includes('.venv/') || normalized.includes('__pycache__/')) {
    return true;
  }

  // Build output (full directory segments only)
  const segments = normalized.split('/');
  const buildDirs = ['dist', 'build', 'out', 'coverage', '.next', '.cache', '.turbo', 'target', 'obj'];
  for (const seg of segments) {
    if (buildDirs.includes(seg)) return true;
  }

  // Lock files
  if (normalized.endsWith('.lock') || normalized.endsWith('package-lock.json') ||
      normalized.endsWith('yarn.lock') || normalized.endsWith('pnpm-lock.yaml')) {
    return true;
  }

  // Binary/asset files
  const binaryExts = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2',
                      '.ttf', '.eot', '.mp3', '.mp4', '.pdf', '.zip', '.tar', '.gz'];
  for (const ext of binaryExts) {
    if (normalized.toLowerCase().endsWith(ext)) return true;
  }

  // Generated files
  if (normalized.endsWith('.min.js') || normalized.endsWith('.min.css') ||
      normalized.endsWith('.map') || normalized.includes('.generated.')) {
    return true;
  }

  // IDE/editor config
  if (normalized.includes('.idea/') || normalized.includes('.vscode/')) {
    return true;
  }

  // Misc non-source
  if (normalized === 'LICENSE' || normalized.endsWith('.gitignore') ||
      normalized.endsWith('.editorconfig') || normalized.endsWith('.prettierrc') ||
      normalized.includes('.eslintrc') || normalized.endsWith('.log')) {
    return true;
  }

  return false;
}

// Step 3: Language detection
function detectLanguage(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const name = path.basename(filePath).toLowerCase();

  const langMap = {
    '.ts': 'typescript', '.tsx': 'typescript',
    '.js': 'javascript', '.jsx': 'javascript',
    '.py': 'python',
    '.go': 'go',
    '.rs': 'rust',
    '.java': 'java',
    '.rb': 'ruby',
    '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp', '.h': 'cpp', '.hpp': 'cpp',
    '.c': 'c',
    '.cs': 'csharp',
    '.swift': 'swift',
    '.kt': 'kotlin',
    '.php': 'php',
    '.vue': 'vue',
    '.svelte': 'svelte',
    '.sh': 'shell', '.bash': 'shell',
    '.md': 'markdown', '.rst': 'markdown',
    '.yaml': 'yaml', '.yml': 'yaml',
    '.json': 'json',
    '.toml': 'toml',
    '.sql': 'sql',
    '.graphql': 'graphql', '.gql': 'graphql',
    '.proto': 'protobuf',
    '.tf': 'terraform', '.tfvars': 'terraform',
    '.html': 'html', '.htm': 'html',
    '.css': 'css', '.scss': 'css', '.sass': 'css', '.less': 'css',
    '.xml': 'xml',
    '.cfg': 'config', '.ini': 'config', '.env': 'config',
    '.txt': 'text'
  };

  if (name === 'dockerfile') return 'dockerfile';
  if (name === 'makefile') return 'makefile';
  if (name === 'jenkinsfile') return 'jenkinsfile';

  return langMap[ext] || 'unknown';
}

// Step 4: File category detection
function detectCategory(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const name = path.basename(filePath).toLowerCase();
  const normalized = filePath.replace(/\\/g, '/');

  // Docs
  if (['.md', '.rst'].includes(ext) && name !== 'license') return 'docs';
  if (ext === '.txt' && name !== 'license') return 'docs';

  // Infra (check before config since docker-compose.yml matches both)
  if (name.startsWith('dockerfile') || name.startsWith('docker-compose')) return 'infra';
  if (['.tf', '.tfvars'].includes(ext)) return 'infra';
  if (['makefile', 'jenkinsfile', 'procfile', 'vagrantfile'].includes(name)) return 'infra';
  if (normalized.includes('.github/workflows/') || normalized.includes('.gitlab-ci.yml') ||
      normalized.includes('.circleci/')) return 'infra';
  if (normalized.includes('k8s/') || normalized.includes('kubernetes/')) return 'infra';
  if (normalized.endsWith('.k8s.yaml') || normalized.endsWith('.k8s.yml')) return 'infra';

  // Data
  if (['.sql', '.graphql', '.gql', '.proto', '.prisma'].includes(ext)) return 'data';
  if (normalized.endsWith('.schema.json') || ext === '.csv') return 'data';

  // Script
  if (['.sh', '.bash', '.ps1', '.bat'].includes(ext)) return 'script';

  // Markup
  if (['.html', '.htm', '.css', '.scss', '.sass', '.less'].includes(ext)) return 'markup';

  // Config
  if (['.yaml', '.yml', '.json', '.toml', '.xml', '.cfg', '.ini', '.env'].includes(ext)) return 'config';
  if (['tsconfig.json', 'package.json', 'pyproject.toml', 'cargo.toml', 'go.mod', 'requirements.txt'].includes(name)) return 'config';

  // Default to code
  return 'code';
}

// Step 5: Line counting
function countLines(root, filePath) {
  try {
    const fullPath = path.join(root, filePath);
    const content = fs.readFileSync(fullPath, 'utf-8');
    return content.split('\n').length;
  } catch (e) {
    return 0;
  }
}

// Step 6: Framework detection
function detectFrameworks(root) {
  const frameworks = new Set();

  // Check package.json
  const pkgPath = path.join(root, 'package.json');
  if (fs.existsSync(pkgPath)) {
    try {
      const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8'));
      const deps = { ...pkg.dependencies, ...pkg.devDependencies };

      const jsFrameworks = {
        'react': 'React', 'vue': 'Vue', 'svelte': 'Svelte', '@angular/core': 'Angular',
        'express': 'Express', 'fastify': 'Fastify', 'koa': 'Koa',
        'next': 'Next.js', 'nuxt': 'Nuxt.js', 'vite': 'Vite',
        'vitest': 'Vitest', 'jest': 'Jest', 'mocha': 'Mocha',
        'tailwindcss': 'Tailwind CSS', 'prisma': 'Prisma',
        'typeorm': 'TypeORM', 'sequelize': 'Sequelize', 'mongoose': 'Mongoose',
        'redux': 'Redux', 'zustand': 'Zustand', 'mobx': 'MobX',
        'langchain': 'LangChain', '@langchain/core': 'LangChain',
        'langgraph': 'LangGraph', 'litellm': 'LiteLLM'
      };

      for (const [dep, name] of Object.entries(jsFrameworks)) {
        if (deps[dep]) frameworks.add(name);
      }
    } catch (e) {}
  }

  // Check requirements.txt
  const reqPath = path.join(root, 'requirements.txt');
  if (fs.existsSync(reqPath)) {
    try {
      const content = fs.readFileSync(reqPath, 'utf-8');
      const pyFrameworks = {
        'django': 'Django', 'djangorestframework': 'Django REST Framework',
        'fastapi': 'FastAPI', 'flask': 'Flask',
        'sqlalchemy': 'SQLAlchemy', 'alembic': 'Alembic',
        'celery': 'Celery', 'pydantic': 'Pydantic',
        'uvicorn': 'Uvicorn', 'gunicorn': 'Gunicorn',
        'pytest': 'pytest', 'langchain': 'LangChain', 'langgraph': 'LangGraph'
      };

      for (const [pkg, name] of Object.entries(pyFrameworks)) {
        if (content.toLowerCase().includes(pkg)) frameworks.add(name);
      }
    } catch (e) {}
  }

  // Check pyproject.toml
  const pyprojectPath = path.join(root, 'pyproject.toml');
  if (fs.existsSync(pyprojectPath)) {
    try {
      const content = fs.readFileSync(pyprojectPath, 'utf-8');
      const pyFrameworks = {
        'langchain': 'LangChain', 'langgraph': 'LangGraph', 'litellm': 'LiteLLM',
        'fastapi': 'FastAPI', 'flask': 'Flask', 'pydantic': 'Pydantic'
      };

      for (const [pkg, name] of Object.entries(pyFrameworks)) {
        if (content.toLowerCase().includes(pkg)) frameworks.add(name);
      }
    } catch (e) {}
  }

  // Infrastructure tools
  if (fs.existsSync(path.join(root, 'Dockerfile'))) frameworks.add('Docker');
  if (fs.existsSync(path.join(root, 'docker-compose.yml')) ||
      fs.existsSync(path.join(root, 'docker-compose.yaml'))) {
    frameworks.add('Docker Compose');
  }

  const workflowsDir = path.join(root, '.github', 'workflows');
  if (fs.existsSync(workflowsDir)) {
    const workflows = fs.readdirSync(workflowsDir).filter(f => f.endsWith('.yml') || f.endsWith('.yaml'));
    if (workflows.length > 0) frameworks.add('GitHub Actions');
  }

  return Array.from(frameworks).sort();
}

// Step 7: Complexity estimation
function estimateComplexity(fileCount) {
  if (fileCount <= 30) return 'small';
  if (fileCount <= 150) return 'moderate';
  if (fileCount <= 500) return 'large';
  return 'very-large';
}

// Step 8: Project name
function getProjectName(root) {
  const pkgPath = path.join(root, 'package.json');
  if (fs.existsSync(pkgPath)) {
    try {
      const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8'));
      if (pkg.name) return pkg.name;
    } catch (e) {}
  }

  const pyprojectPath = path.join(root, 'pyproject.toml');
  if (fs.existsSync(pyprojectPath)) {
    try {
      const content = fs.readFileSync(pyprojectPath, 'utf-8');
      const match = content.match(/name\s*=\s*["']([^"']+)["']/);
      if (match) return match[1];
    } catch (e) {}
  }

  return path.basename(root);
}

// Get description
function getDescription(root) {
  const pkgPath = path.join(root, 'package.json');
  if (fs.existsSync(pkgPath)) {
    try {
      const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8'));
      if (pkg.description) return pkg.description;
    } catch (e) {}
  }

  const readmePath = path.join(root, 'README.md');
  if (fs.existsSync(readmePath)) {
    try {
      const content = fs.readFileSync(readmePath, 'utf-8');
      const lines = content.split('\n').slice(0, 10);
      return lines.join('\n');
    } catch (e) {}
  }

  return '';
}

// Step 9: Import resolution
function resolveImports(root, files, fileCategory) {
  const importMap = {};
  const filePathSet = new Set(files.map(f => f.path));

  for (const file of files) {
    importMap[file.path] = [];

    // Only process code files
    if (fileCategory[file.path] !== 'code') continue;

    const lang = file.language;
    if (!['typescript', 'javascript', 'python', 'go', 'rust', 'ruby'].includes(lang)) continue;

    try {
      const content = fs.readFileSync(path.join(root, file.path), 'utf-8');
      const dir = path.dirname(file.path);
      const ext = path.extname(file.path);

      if (lang === 'typescript' || lang === 'javascript') {
        // Match import ... from './...' or './...'
        const importRegex = /(?:import\s+[^'"]*from\s+|require\s*\(\s*)['"](\.[^'"]+)['"]/g;
        let match;
        while ((match = importRegex.exec(content)) !== null) {
          const importPath = match[1];
          const resolved = resolvePath(dir, importPath, ext, filePathSet);
          if (resolved && filePathSet.has(resolved)) {
            importMap[file.path].push(resolved);
          }
        }
      } else if (lang === 'python') {
        // Match relative imports
        const importRegex = /from\s+(\.\S+)\s+import|from\s+(\.)\s+import/g;
        let match;
        while ((match = importRegex.exec(content)) !== null) {
          const importPath = match[1] || match[2];
          const resolved = resolvePath(dir, importPath, '.py', filePathSet);
          if (resolved && filePathSet.has(resolved)) {
            importMap[file.path].push(resolved);
          }
        }
      }
    } catch (e) {}
  }

  return importMap;
}

function resolvePath(dir, importPath, sourceExt, filePathSet) {
  const extensions = ['.ts', '.tsx', '.js', '.jsx', '.py', '.go', '.rs', '.rb'];
  const indexPaths = ['/index.ts', '/index.js', '/index.tsx', '/index.jsx'];

  let resolved = path.join(dir, importPath).replace(/\\/g, '/');

  // Try exact path first
  if (filePathSet.has(resolved)) return resolved;

  // Try with extensions
  for (const ext of extensions) {
    const withExt = resolved + ext;
    if (filePathSet.has(withExt)) return withExt;
  }

  // Try index files
  for (const idx of indexPaths) {
    const withIdx = resolved + idx;
    if (filePathSet.has(withIdx)) return withIdx;
  }

  return null;
}

// Main execution
try {
  const allFiles = discoverFiles(projectRoot);
  const filteredFiles = allFiles.filter(f => !shouldExclude(f));

  const fileCategory = {};
  const files = [];

  for (const filePath of filteredFiles) {
    const lang = detectLanguage(filePath);
    const cat = detectCategory(filePath);
    const lines = countLines(projectRoot, filePath);

    fileCategory[filePath] = cat;
    files.push({
      path: filePath,
      language: lang,
      sizeLines: lines,
      fileCategory: cat
    });
  }

  // Sort by path
  files.sort((a, b) => a.path.localeCompare(b.path));

  // Get unique languages
  const languages = [...new Set(files.map(f => f.language))].filter(l => l !== 'unknown').sort();

  // Get frameworks
  const frameworks = detectFrameworks(projectRoot);

  // Get project name
  const name = getProjectName(projectRoot);

  // Get description
  const rawDescription = getDescription(projectRoot);

  // Read README head
  let readmeHead = '';
  const readmePath = path.join(projectRoot, 'README.md');
  if (fs.existsSync(readmePath)) {
    try {
      const content = fs.readFileSync(readmePath, 'utf-8');
      readmeHead = content.split('\n').slice(0, 10).join('\n');
    } catch (e) {}
  }

  // Resolve imports
  const importMap = resolveImports(projectRoot, files, fileCategory);

  const result = {
    scriptCompleted: true,
    name,
    rawDescription,
    readmeHead,
    languages,
    frameworks,
    files,
    totalFiles: files.length,
    filteredByIgnore: 0,
    estimatedComplexity: estimateComplexity(files.length),
    importMap
  };

  fs.writeFileSync(outputFile, JSON.stringify(result, null, 2));
  console.log(`Scan complete: ${files.length} files found`);
  process.exit(0);
} catch (error) {
  console.error('Error:', error.message);
  process.exit(1);
}
