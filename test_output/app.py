from flask import Flask, render_template

app = Flask(__name__)


@app.route('/')
def index():
    """Home page route."""
    return render_template('index.html')


@app.route('/api/status')
def status():
    """API status endpoint."""
    return {'status': 'ok', 'message': 'Flask application is running'}


@app.route('/api/greet/<name>')
def greet(name):
    """Greeting API endpoint."""
    return {'message': f'Hello, {name}!', 'name': name}


if __name__ == '__main__':
    app.run(debug=True, port=5000)
