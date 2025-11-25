#!/usr/bin/env python3
"""
Railway startup script
Starts uvicorn with PORT from environment variable
"""
import os
import sys

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))

    # Import uvicorn and run
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
