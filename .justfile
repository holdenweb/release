project := `uv version | awk '{print $1}'`
version := `uv version | awk '{print $2}'`

test:
    #!/usr/bin/env bash
    set -euo pipefail
    function check () {
        v=$(uv version | awk '{print $2}')
        if [ "$v" != "$1" ]
        then
            echo Ouch - should be "$1" but is actually "$v"
            exit 1
        fi
    }
    echo uv project is $(uv version | awk '{print $1}')

    # set up a temp working directory and a trap to remove it when exiting
    save_dir=$(pwd)
    tmp_dir=$(mktemp -d)
    trap "cd $save_dir; rm -rf $tmp_dir" EXIT
    echo running in $tmp_dir
    cd $tmp_dir

    # Create a new project and place under git control
    uv init --lib test-project
    cd test-project
    git init
    git add * .gitignore .python-version
    git commit -m "As created"
    release patch alpha
    check 0.1.1a1
    release alpha
    check 0.1.1a2
    release beta
    check 0.1.1b1
    release major
    check 1.0.0

    git status
    git tag
    git log

install:
    @echo {{version}} {{project}}
    uv tool install -U dist/{{project}}-{{version}}-py3-none-any.whl






