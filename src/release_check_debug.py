GUILTY_STRING = "import" + " wingdbstub"

def vet(c_file):
    if any(c_file.path.endswith(x for x in (".py", ".pyw"))):
        if GUILTY_STRING in c_file.read_text():
            return "still includes wingdbstub imports"
