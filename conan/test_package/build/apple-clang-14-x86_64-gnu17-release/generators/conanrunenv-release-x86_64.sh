echo "echo Restoring environment" > "/Users/ejoliet/devspace/playground/conan/test_package/build/apple-clang-14-x86_64-gnu17-release/generators/deactivate_conanrunenv-release-x86_64.sh"
for v in 
do
    is_defined="true"
    value=$(printenv $v) || is_defined="" || true
    if [ -n "$value" ] || [ -n "$is_defined" ]
    then
        echo export "$v='$value'" >> "/Users/ejoliet/devspace/playground/conan/test_package/build/apple-clang-14-x86_64-gnu17-release/generators/deactivate_conanrunenv-release-x86_64.sh"
    else
        echo unset $v >> "/Users/ejoliet/devspace/playground/conan/test_package/build/apple-clang-14-x86_64-gnu17-release/generators/deactivate_conanrunenv-release-x86_64.sh"
    fi
done

