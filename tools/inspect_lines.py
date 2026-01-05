from pathlib import Path
import sys
p=Path(r"c:\Users\PC\Desktop\System-Flow\attendance\views.py")
b= p.read_bytes().splitlines()
start=3308
end=3500
b=p.read_bytes().splitlines()
for i in range(start,end):
    line=b[i]
    # count leading spaces
    lead=len(line)-len(line.lstrip(b" \t"))
    print(f"{i+1}: lead={lead} bytes={repr(line)}")
