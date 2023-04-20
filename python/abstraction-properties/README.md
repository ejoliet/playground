# README

Make the main executable read the condition from an external property file to decide if it’s file or db serializer , using POJO Gaia object

The config.json file contains the configuration details for the serializer. Here's an example config.json file for using a file serializer.

Note that the SerializerFactory class has been modified to take the config parameter in the create_serializer method, which contains the configuration details for the serializer. The serializer_type parameter is read from the config dictionary, and used to determine which serializer to create. The serializer_config parameter is then used to provide the configuration details specific to the serializer being created.
