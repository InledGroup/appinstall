#!/usr/bin/python3
import sys
import os

# Añadir el directorio actual al path para que encuentre el paquete src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.main import main

if __name__ == "__main__":
    sys.exit(main())
