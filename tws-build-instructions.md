# TWS API Build Instructions

## Prerequisites

- Python 3.8+
- Virtual environment activated

## Build and Install Steps

1. **Install build dependencies**

   ```bash
   pip install setuptools wheel
   ```

2. **Build the ibapi package**

   ```bash
   cd contrib/IBJts/source/pythonclient
   python setup.py sdist bdist_wheel
   ```

3. **Install the built package**

   ```bash
   pip install dist/ibapi-10.30.1-py3-none-any.whl
   ```

4. **Verify installation**

   ```bash
   python -c "from ibapi.client import EClient; print('ibapi installed successfully')"
   ```

## Notes

- This builds ibapi version 10.30.1 from the local TWS API source in `contrib/`
- The wheel file will be created in `contrib/IBJts/source/pythonclient/dist/` directory
- Use this instead of `pip install ibapi` to get the exact version matching your TWS installation