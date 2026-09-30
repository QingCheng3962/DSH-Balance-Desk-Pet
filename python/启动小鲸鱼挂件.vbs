' DSH 小鲸鱼桌面挂件 —— 双击启动（无控制台窗口）
' 用 pythonw 拉起主程序；找不到 pythonw 时退回 python。
Option Explicit

Dim fso, shell, here, target, exe
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

here = fso.GetParentFolderName(WScript.ScriptFullName)
target = here & "\dsh_whale_pet.py"

If Not fso.FileExists(target) Then
  MsgBox "找不到 dsh_whale_pet.py：" & target, 16, "DSH 小鲸鱼桌面挂件"
  WScript.Quit 1
End If

shell.CurrentDirectory = here
exe = "pythonw.exe"
shell.Run """" & exe & """ """ & target & """", 0, False
