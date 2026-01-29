Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\chrni\Desktop\projects\claude\soccer-props-value"
WshShell.Run "python -u auto_scanner.py", 0, False
