#!/bin/bash
gunicorn -w 1 -k gthread --threads 4 --timeout 300 app:app -b 0.0.0.0:5000
