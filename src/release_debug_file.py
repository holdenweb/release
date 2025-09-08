def vet(c_file):
    if c_file.endswith("/wingdbstub.py"):
        return "is a debug file"
