def vet(c_file):
    if c_file.path.endswith("/wingdbstub.py"):
        return "is a debug file"
