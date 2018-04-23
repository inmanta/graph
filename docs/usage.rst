Graph module usage
==================

The graph module provides an exporter that generates dot and png files based on a diagram definition.

.. warning:: This module is experimental code. It will not affect the result of what will be deployed. However the generation
             of diagram may not work very consist.

Install
-------

Add in the .inmanta file of your project in the config section graph to the export option. For example:

  [config]
  environment=f603387a-f1af-4148-a286-c4d309ef4ada
  export=graph

When `inmanta export` is called, the compiler will not only send the resources to the orchestration server but also
call the graph export plugin.

Settings
--------

The plugin has settings that can be added to the inmanta config file (.inmanta or other specified). All settings are set in the
[graph] section.

- output-dir: The location where all the generated graphs are stored.
- types: A list of file types that should be generated. By default a png is generated. This list can contain multiple values
         seperated with commas. If only the dot file is required an empty value should be provided.

Diagram definition
------------------

The export plugin searches in the complete configuration module to instances of graph::Graph. This instance defines the name
of the generated file and a config attribute that provides the graph instruction by means of a very limited DSL.

Each line of the diagram DSL can contain empty lines, comments (start with #), an entity type with optional settings
and relation definitions also with optional settings. The DSL selects both the entity instances and relations between these
instances to show in a diagram.

Entity type
^^^^^^^^^^^
Select all instance of a certain entity by specifying the full name of the type.

Between square brackets options can be specified:
    - label: The label of the instances. It can be either an attribute of the entity or a string indicated with double
             quotes. This string can contain formatters between curly braces {}. Between these braces name of the attributes
             can be used.

For example:
```
std::File[label=path]
std::Service[label="Service name {name}"]
```

Entity relations
^^^^^^^^^^^^^^^^

With the full name of the entity and the name of the relation, edges between instances are added to the graph.

Between square brackets options can be specified:
    - label: The label on the edge. Either the name of the attribute when nothing is specified or a string with double quotes.