Graph module usage
==================

The graph module provides two exporters:
1. class diagram exporter to convert inmanta model into a [plantuml](https://plantuml.com/) class diagram
2. an instance diagram exporter that generates dot and png files based on a diagram definition.

.. warning:: This module is experimental code. It will not affect the result of what will be deployed. However the generation
             of diagram may not work very consist.

Class Diagrams
---------------

Add following snippet to your model:

.. code-block:: inmanta

  graph::ClassDiagram(name="my_diagram", moduleexpression=["std::.*"], header="""
  skinparam monochrome true
  skinparam shadowing false
  set namespaceSeparator ::
  left to right direction""")


then export using 

.. code-block:: bash
  
  inmanta -vv export  -j x.json --export-plugin=classdiagram
  plantuml my_diagram.puml -tsvg

This will produce a class diagram for the module 'std'.

Diagram definition
-------------------

Add following snippet to your model:

.. code-block:: bash
  graph::Graph(name="my_graph", config=std::source("/files_and_hosts.g"))

Add the graph filter file `./files/files_and_hosts.g`

.. code-block:: 
  
  std::Host
  std::File
  std::File.host

This will filter all `std::Host` and `std::File` instance out of the model and add them to the graph. 
The statement `std::File.host` will add all the `host` relations of all the files to the graph as well. 

to generate the graph

.. code-block:: bash
  
  inmanta -vv export  -j x.json --export-plugin=graph

This will create a file `my_graph.dot` and `my_graph.png`

Install
-------

Add in the .inmanta file of your project in the config section graph to the export option. For example:

.. code-block:: config

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
    - container: If set to true, this node will be treated as a container that can contain other nodes. See, type=contained_in

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
    - type: This can changes the relation type. The options are:
        * contained_in: This means that this relation indicates that the node should be placed inside the target node of the
                        relation.