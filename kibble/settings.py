# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import os

from kibble.configuration import conf

YAML_DIRECTORY = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "api", "yaml"
)
KIBBLE_YAML = os.path.join(YAML_DIRECTORY, "kibble.yaml")
MAPPING_DIRECTORY = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "mappings"
)

WATSON_ENABLED = bool(conf.get("watson", "username", fallback=None))
AZURE_ENABLED = bool(conf.get("azure", "apikey", fallback=None))
PICOAPI_ENABLED = bool(conf.get("picoapi", "key", fallback=None))
