"""Clean build script — run from asic_suite/ directory."""
import subprocess, sys, os, shutil, stat

def remove_readonly(fn, path, _):
    os.chmod(path, stat.S_IWRITE)
    fn(path)

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

for d in ("build", "dist"):
    if os.path.exists(d):
        shutil.rmtree(d, onerror=remove_readonly)
        print(f"Removed {d}/")

pyi = r"C:\Users\royf1\anaconda3\envs\varification_model\Scripts\pyinstaller.exe"
result = subprocess.run([pyi, "main.spec"], capture_output=True, text=True)
print("--- STDOUT ---")
print(result.stdout[-4000:] if len(result.stdout) > 4000 else result.stdout)
print("--- STDERR ---")
print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
print("Return code:", result.returncode)
if result.returncode == 0:
    print("BUILD SUCCESS")
else:
    print("BUILD FAILED")
