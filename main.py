import os
import subprocess
import sys

if __name__ == "__main__":
    node_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.js")
    subprocess.run(["node", node_script] + sys.argv[1:])
