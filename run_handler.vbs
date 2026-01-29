Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\chrni\Desktop\projects\claude\soccer-props-value"
WshShell.Run "python -u telegram_handler.py", 0, False
