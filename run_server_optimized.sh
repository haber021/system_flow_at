#!/bin/bash

echo "========================================"
echo "Starting Optimized Django Server"
echo "========================================"
echo ""
echo "Server will be accessible from mobile devices at:"
echo "  http://YOUR_IP_ADDRESS:8000"
echo ""
echo "To find your IP address, run: ifconfig or ip addr"
echo ""
echo "Press CTRL+C to stop the server"
echo "========================================"
echo ""

python manage.py runserver 0.0.0.0:8000

