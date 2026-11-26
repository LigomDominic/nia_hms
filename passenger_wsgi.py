import os
import sys

# cPanel "Setup Python App" runs this file with the app root as the working directory.
# Keep this file at the top level of the application root.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hms import create_app

application = create_app()
