# Test Suite for ibi Recovery Toolkit

Comprehensive test suite for the ibi database recovery toolkit, ensuring reliability and correctness of recovery operations.

## 🧪 Test Structure

### Test Categories

- **`test_database_operations.py`** - Database connection, querying, and data retrieval
- **`test_file_operations.py`** - File verification, copying, and availability checking
- **`test_export_functionality.py`** - Metadata export and format generation
- **`test_cli_interface.py`** - Command-line interface and argument parsing
- **`test_reference_implementation.py`** - Reference API for developers
- **`test_export_formats.py`** - Export format configuration validation

### Test Fixtures

- **Mock ibi structure** - Simulated ibi directory with database and files
- **Sample database** - SQLite database with realistic test data
- **Mock files** - Test files matching database content IDs
- **Export configurations** - Test export format specifications

## 🚀 Running Tests

### Quick Start

```bash
# Run all tests
python run_tests.py

# Run specific test categories
python run_tests.py database    # Database operations only
python run_tests.py export      # Export functionality only
python run_tests.py cli         # CLI interface only

# Run with coverage
python run_tests.py --coverage

# Run fast tests only (skip slow integration tests)
python run_tests.py fast
```

### Using pytest directly

```bash
# All tests
pytest

# Specific test file
pytest tests/test_database_operations.py

# Specific test method
pytest tests/test_database_operations.py::TestDatabaseOperations::test_connect_to_database_success

# With coverage
pytest --cov=ibirecovery --cov-report=html
```

### Using Poetry

```bash
# Install test dependencies
poetry install --group dev

# Run tests
poetry run pytest

# Run with optional dependencies
poetry install --extras metadata
poetry run pytest
```

## 📊 Test Data

### Mock Database Schema

The test suite creates realistic SQLite databases with:

- **4 test files** (JPEG, MP4, PNG, and one missing file)
- **2 albums** ("Family Vacation", "Work Photos")
- **5 AI content tags** (person, beach, vacation, document)
- **GPS coordinates** for 2 files
- **Camera EXIF** data (Canon EOS R5, Sony A7R IV)

### Test Coverage Areas

#### Database Operations ✅

- ibi directory structure detection
- SQLite database connection and querying
- File metadata retrieval with albums and tags
- GPS coordinate and camera EXIF data parsing
- Statistics generation and data consistency

#### File Operations ✅

- File availability verification (sample and comprehensive)
- Resume-capable file copying with progress tracking
- MIME type categorization and size formatting
- Missing file detection and reporting
- File path construction from content IDs

#### Export Functionality ✅

- Metadata export in 12+ standard formats
- CSV generation (Lightroom, digiKam, ExifTool, etc.)
- JSON metadata export (Google Takeout, API format)
- XMP sidecar file creation
- Video management formats (Jellyfin, Plex)
- Unicode handling and file naming

#### CLI Interface ✅

- Command-line argument parsing and validation
- Verification, export, and extraction modes
- Progress reporting and error handling
- Integration with subprocess calls
- Help and format listing functionality

#### Reference Implementation ✅

- Developer API consistency and documentation
- Context manager support and error handling
- Performance characteristics and data consistency
- Integration with main toolkit functionality

## 🏗️ Test Infrastructure

### Fixtures and Mocks

```python
# Available fixtures for test development
@pytest.fixture
def temp_dir():          # Temporary directory for test files
def mock_ibi_structure(temp_dir):  # Simulated ibi directory structure
def mock_database(mock_ibi_structure):  # SQLite with test data
def mock_files(mock_ibi_structure):     # Physical test files
def sample_files_data():                # Sample file metadata
def mock_export_formats(temp_dir):      # Export format configurations
```

### Test Utilities

- **Dependency checking** - Validates required and optional dependencies
- **Performance timing** - Ensures operations complete within reasonable time
- **Data consistency** - Verifies consistency across different query methods
- **Unicode handling** - Tests international character support
- **Error simulation** - Tests graceful handling of various error conditions

## 🔧 Development Guidelines

### Adding New Tests

1. **Follow naming conventions** - Use `test_` prefix for functions and files
2. **Use appropriate fixtures** - Leverage existing mocks and test data
3. **Test both success and failure** - Include error condition testing
4. **Add markers** - Use `@pytest.mark.slow` for long-running tests
5. **Document test purpose** - Clear docstrings explaining what is tested

### Test Categories (Markers)

```python
@pytest.mark.unit          # Fast, isolated unit tests
@pytest.mark.integration   # Slower tests with external dependencies
@pytest.mark.cli           # Command-line interface tests
@pytest.mark.database      # Database operation tests
@pytest.mark.export        # Export functionality tests
@pytest.mark.slow          # Tests that take >5 seconds
@pytest.mark.requires_pillow  # Tests needing PIL/Pillow library
```

### Performance Expectations

- **Unit tests**: < 1 second each
- **Integration tests**: < 10 seconds each
- **Full test suite**: < 2 minutes
- **Database operations**: < 1 second for test data
- **File operations**: < 5 seconds for mock files

## 📈 Continuous Integration

The test suite is designed for CI/CD environments:

- **No external dependencies** - All required resources are mocked
- **Deterministic results** - Tests produce consistent results
- **Parallel execution** - Tests can run concurrently
- **Clear failure reporting** - Detailed error messages and stack traces
- **Coverage reporting** - Tracks test coverage across codebase

### CI Command Examples

```bash
# Basic CI test run
pytest --tb=short --disable-warnings

# With coverage for CI
pytest --cov=ibirecovery --cov-report=xml --cov-fail-under=80

# Fast tests only for PR checks
pytest -m "not slow" --tb=line
```

## 🐛 Debugging Test Failures

### Common Issues

1. **Import errors** - Ensure `ibirecovery` package is in Python path
2. **Missing fixtures** - Check that required fixtures are properly imported
3. **File permissions** - Ensure test has write access to temporary directories
4. **Mock data inconsistency** - Verify mock database matches expected test data

### Debug Tools

```bash
# Run single test with full output
pytest tests/test_file_operations.py::TestFileVerification::test_verify_file_availability_all_present -vvv -s

# Drop into debugger on failure
pytest --pdb tests/test_database_operations.py

# Show local variables on failure
pytest --tb=long tests/
```

## 📚 Resources

- **pytest documentation**: https://docs.pytest.org/
- **Test data generation**: See `conftest.py` for fixture examples
- **Mocking strategies**: Examples in each test file
- **Performance testing**: See `test_reference_implementation.py`
