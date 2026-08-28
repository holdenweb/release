project := `uv version | awk '{print $1}'`
version := `uv version | awk '{print $2}'`
# The version named by the most recent release tag. The working tree runs ahead
# of this on a .dev version between releases, so `install` deliberately installs
# the last *release* rather than whatever pyproject.toml currently says.
tag := `git describe --tags --abbrev=0`
released := `git describe --tags --abbrev=0 | sed "s/^${RELEASE_TAG_PREFIX-r}//"`

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

# Build the last tagged release into dist/, from the tag rather than the tree.
build-release:
    #!/usr/bin/env bash
    set -euo pipefail
    # Between releases the working tree runs ahead on a .dev version, so the
    # artifact must come from the tag, not from pyproject.toml as it stands.
    tmp_dir=$(mktemp -d)
    trap "rm -rf $tmp_dir" EXIT
    echo "building {{project}} {{released}} from tag {{tag}}"
    git archive {{tag}} | tar -x -C "$tmp_dir"
    uv build "$tmp_dir" --out-dir dist

install: build-release
    @echo "installing {{project}} {{released}} (working tree is at {{version}})"
    uv tool install -U dist/{{project}}-{{released}}-py3-none-any.whl






