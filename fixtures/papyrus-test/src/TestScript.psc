Scriptname TestScript extends Quest
{Minimal Session 4 fixture for Caprica vs CK PapyrusCompiler bytecode diff.}

Event OnInit()
    Debug.Trace("Session 4 TestScript online")
EndEvent

Function Greet(string name)
    Debug.Trace("Hello, " + name)
EndFunction

int Function Add(int a, int b)
    return a + b
EndFunction
