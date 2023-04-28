# README

## create package following 

optional: using user/channel

> conan new cmake_lib -d name=hello -d version=1.0 -d user=roman-msos -d channel=dev
> conan create . --user roman-msos --channel dev

This will create a package to be uploaded to roman-msos/channel 
without, it will be hello/1.0@_/_

See more:
https://docs.conan.io/2/tutorial/creating_packages/create_your_first_package.html

If problems with conan install, use virtualenvwrapper to create an env to get conan 2.0
see https://docs.conan.io/1/faq/troubleshooting.html#error-failed-to-create-process

## CMake
https://cmake.org/install/


## Setting up conan server to upload package

see https://docs.conan.io/2/tutorial/conan_repositories/setting_up_conan_remotes/artifactory/artifactory_ce_cpp.html#artifactory-ce-cpp

In nutshell:
Run Conan server.
Add project roman-msos-photmetry, key : msos
Add user
Add group
Add repository roman-msos-photometry
Add remote server to autehticate user

conan remote add <name-key> http://localhost:8088/artifactory/api/conan/<name-repos>

conan remote login <name-key> <user>

### Search

See packages from:

#### CLI:

conan search "*" -r=<name-key>

#### in browser:

http://localhost:8088/ui/native/<name-repos>

## upload package with user/channel

conan upload hello -r=<name-key>

With user/channel:

conan upload hello/1.0@roman-msos/dev -r=<name-key>

Ex: 
conan upload hello/1.0@roman-msos/dev -r=msos

## search a package

conan search "hello" -r=<name-key>

Example:
> conan search "*" -r msos

returns:

msos
  hello
    hello/1.0
    hello/1.0@roman-msos/dev

## install

conan install --requires=hello/1.0 -r=<name-key>

