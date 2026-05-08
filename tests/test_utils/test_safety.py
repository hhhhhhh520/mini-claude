"""Unit tests for safety utilities - sensitive input detection."""

import pytest

from mini_claude.utils.safety import SafetyChecker, check_sensitive_input


class TestSensitivePatterns:
    """Test sensitive information pattern detection."""

    def test_detect_api_key_sk_prefix(self):
        """Test detection of OpenAI-style API key with sk- prefix."""
        result = check_sensitive_input("My API key is sk-1234567890abcdef")
        assert result["detected"] is True
        assert "api_key" in result["patterns"]

    def test_detect_api_key_in_url(self):
        """Test detection of API key in URL parameter."""
        result = check_sensitive_input("https://api.example.com?api_key=secret123")
        assert result["detected"] is True
        assert "api_key" in result["patterns"]

    def test_detect_x_api_key_header(self):
        """Test detection of x-api-key header pattern."""
        result = check_sensitive_input("x-api-key: my-secret-key-12345")
        assert result["detected"] is True
        assert "api_key" in result["patterns"]

    def test_detect_password_assignment(self):
        """Test detection of password assignment."""
        result = check_sensitive_input("password=MySecretPass123")
        assert result["detected"] is True
        assert "password" in result["patterns"]

    def test_detect_passwd_assignment(self):
        """Test detection of passwd assignment."""
        result = check_sensitive_input("passwd=secret")
        assert result["detected"] is True
        assert "password" in result["patterns"]

    def test_detect_pwd_assignment(self):
        """Test detection of pwd assignment."""
        result = check_sensitive_input("pwd=admin123")
        assert result["detected"] is True
        assert "password" in result["patterns"]

    def test_detect_bearer_token(self):
        """Test detection of Bearer token."""
        result = check_sensitive_input("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
        assert result["detected"] is True
        assert "token" in result["patterns"]

    def test_detect_token_assignment(self):
        """Test detection of token assignment."""
        result = check_sensitive_input("token=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        assert result["detected"] is True
        assert "token" in result["patterns"]

    def test_detect_jwt_token(self):
        """Test detection of JWT token."""
        result = check_sensitive_input("jwt eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")
        assert result["detected"] is True
        assert "token" in result["patterns"]

    def test_detect_mysql_connection_string(self):
        """Test detection of MySQL connection string with password."""
        result = check_sensitive_input("mysql://user:password123@localhost:3306/mydb")
        assert result["detected"] is True
        assert "connection_string" in result["patterns"]

    def test_detect_postgresql_connection_string(self):
        """Test detection of PostgreSQL connection string with password."""
        result = check_sensitive_input("postgresql://admin:secretpass@db.example.com:5432/production")
        assert result["detected"] is True
        assert "connection_string" in result["patterns"]

    def test_detect_multiple_patterns(self):
        """Test detection of multiple sensitive patterns."""
        result = check_sensitive_input("api_key=sk-12345&password=secret&token=abc123")
        assert result["detected"] is True
        assert len(result["patterns"]) >= 2
        assert "api_key" in result["patterns"]
        assert "password" in result["patterns"]

    def test_no_detection_for_normal_text(self):
        """Test that normal text is not flagged."""
        result = check_sensitive_input("This is a normal sentence about API design.")
        assert result["detected"] is False
        assert result["patterns"] == []

    def test_no_detection_for_api_word_alone(self):
        """Test that 'api' word alone doesn't trigger false positive."""
        result = check_sensitive_input("I'm building an API for my application")
        assert result["detected"] is False

    def test_no_detection_for_password_discussion(self):
        """Test that discussing passwords without actual values is safe."""
        result = check_sensitive_input("You should use a strong password for security")
        assert result["detected"] is False

    def test_no_detection_for_bearer_word_alone(self):
        """Test that 'bearer' word alone doesn't trigger false positive."""
        result = check_sensitive_input("The bearer of this document is authorized")
        assert result["detected"] is False

    def test_no_false_positive_on_mysql_word(self):
        """Test that 'mysql' word alone doesn't trigger false positive."""
        result = check_sensitive_input("I'm using MySQL database for my project")
        assert result["detected"] is False

    def test_severity_levels(self):
        """Test severity level assignment."""
        # High severity: API keys and connection strings
        result = check_sensitive_input("sk-proj-1234567890abcdefghijklmnopqrstuvwxyz")
        assert result["severity"] == "high"

        # High severity: connection strings with credentials
        result = check_sensitive_input("mysql://root:password@localhost/db")
        assert result["severity"] == "high"

        # Medium severity: password assignments
        result = check_sensitive_input("password=test123")
        assert result["severity"] in ["high", "medium"]

    def test_case_insensitive_detection(self):
        """Test that detection is case-insensitive."""
        result = check_sensitive_input("API_KEY=secret123")
        assert result["detected"] is True

        result = check_sensitive_input("PASSWORD=admin")
        assert result["detected"] is True

        result = check_sensitive_input("BEARER token123")
        assert result["detected"] is True


class TestSafetyCheckerIntegration:
    """Test SafetyChecker integration with sensitive input detection."""

    def test_safety_checker_has_sensitive_check(self):
        """Test that SafetyChecker has check_sensitive method."""
        checker = SafetyChecker()
        assert hasattr(checker, "check_sensitive")

    def test_safety_checker_check_sensitive_returns_result(self):
        """Test that check_sensitive returns proper result."""
        checker = SafetyChecker()
        result = checker.check_sensitive("api_key=secret123")
        assert "detected" in result
        assert "patterns" in result
        assert "severity" in result

    def test_safety_checker_check_sensitive_safe_input(self):
        """Test that safe input returns not detected."""
        checker = SafetyChecker()
        result = checker.check_sensitive("Normal user input")
        assert result["detected"] is False


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string(self):
        """Test handling of empty string."""
        result = check_sensitive_input("")
        assert result["detected"] is False

    def test_whitespace_only(self):
        """Test handling of whitespace-only string."""
        result = check_sensitive_input("   \n\t  ")
        assert result["detected"] is False

    def test_very_long_string_without_secrets(self):
        """Test handling of very long string without secrets."""
        long_text = "This is a normal sentence. " * 1000
        result = check_sensitive_input(long_text)
        assert result["detected"] is False

    def test_secret_at_end_of_string(self):
        """Test detection when secret is at end of string."""
        result = check_sensitive_input("Some normal text followed by api_key=secret")
        assert result["detected"] is True

    def test_secret_at_start_of_string(self):
        """Test detection when secret is at start of string."""
        result = check_sensitive_input("password=secret123 is my password")
        assert result["detected"] is True

    def test_secret_with_surrounding_whitespace(self):
        """Test detection with surrounding whitespace."""
        result = check_sensitive_input("  api_key = secret123  ")
        assert result["detected"] is True

    def test_url_without_password(self):
        """Test that URL without password is not flagged."""
        result = check_sensitive_input("https://example.com/api/data")
        assert result["detected"] is False

    def test_mongodb_connection_string(self):
        """Test detection of MongoDB connection string with credentials."""
        result = check_sensitive_input("mongodb://user:pass123@localhost:27017/mydb")
        assert result["detected"] is True
        assert "connection_string" in result["patterns"]

    def test_redis_connection_string(self):
        """Test detection of Redis connection string with password."""
        result = check_sensitive_input("redis://:mypassword@localhost:6379/0")
        assert result["detected"] is True
        assert "connection_string" in result["patterns"]

    def test_aws_access_key_pattern(self):
        """Test detection of AWS access key pattern."""
        # AWS access keys start with AKIA
        result = check_sensitive_input("AKIAIOSFODNN7EXAMPLE")
        assert result["detected"] is True
        assert "api_key" in result["patterns"]

    def test_github_token_pattern(self):
        """Test detection of GitHub token pattern."""
        # GitHub tokens start with ghp_
        result = check_sensitive_input("ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        assert result["detected"] is True
        assert "token" in result["patterns"]
