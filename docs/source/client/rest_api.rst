.. _rest_api:

REST API
========

HTTP requests can be sent to a Polytope server to submit data requests and poll their status, as well as to retrieve the data once it is ready for download. Although a bit tedious, it is the native, clientless way to interact with the server and it is used behind the scenes by the `polytope-client` Python API and command-line interface.

A basic example workflow is provided below. You can find more details in the :ref:`rest_api_reference` or at the ``/api/v1/openapi`` endpoint of an active polytope server.

Getting started
---------------

First, set up some environment variables to be used throughout the example.

.. code-block:: bash

   export address=https://polytope.example.com
   export port=443
   export url=${address}:${port}
   export user_email=polly@example.com
   export user_key='4j3s3d34n4sn335jacf3n3d4f4g61635'

Check the Polytope server is up and running via GET to the ``/api/v1/test`` endpoint:

.. code-block:: bash

   curl -i $url/api/v1/test
   # HTTP/1.1 200 OK
   # [...]
   # {"message": "Polytope server is alive"}

Check the available collections via GET to the ``/api/v1/collections`` endpoint without authentication:

.. code-block:: bash

   curl -i -X GET $url/api/v1/collections
   # HTTP/1.1 401 UNAUTHORIZED
   # [...]
   # {"message": "Could not read authorization header, expected 'Authorization: <type> <credentials>"}

Repeat with authentication:

.. code-block:: bash

   curl -i -X GET $url/api/v1/collections -H "Authorization: EmailKey $user_email:$user_key"
   # HTTP/1.1 200 OK
   # [...]
   # {"message": ["collection1", "collection2"]}

.. note::
   In this example, EmailKey authentication is used. You can replace it by Basic or Bearer authentication if your Polytope instance is configured with different authentication mechanisms. See :ref:`authentication`.

Making a request
----------------

Submit a request to one of the collections via POST to the ``/api/v1/requests/<collection-id>``` endpoint:

.. code-block:: bash

   request='{"verb":"retrieve","request":{"stream":"oper","levtype":"sfc","param":"165.128/166.128/167.128","step":"0","time":"00/06/12/18","date":"20150323","type":"an","class":"od","expver":"0001","domain":"g"}}'

   curl -i -X POST $url/api/v1/requests/collection1 -H "Authorization: EmailKey $user_email:$user_key" -H "Content-Type: application/json" -d "$request"
   # HTTP/1.1 202 ACCEPTED
   # Location: https://polytope.example.com/api/v1/requests/dc2b6c27-a849-4787-91d0-df8dc9d25440
   # [...]
   # {"message": "Request queued", "status": "queued"}

.. note::
   In this example, we assume that `collection1` uses `FDB` as a datasource. The format of the request is a dictionary  of meteorological keys which this particular FDB understands. See :ref:`collections` and the `FDB documentation <https://github.com/ecmwf/fdb/>`_.

Poll the status of your request via GET to the ``/api/v1/requests/<request-id>`` endpoint:

.. code-block:: bash

   curl -i -X GET $url/api/v1/requests/dc2b6c27-a849-4787-91d0-df8dc9d25440 -H "Authorization: EmailKey $user_email:$user_key"
   # HTTP/1.1 202 ACCEPTED
   # Location: https://polytope.example.com/api/v1/requests/dc2b6c27-a849-4787-91d0-df8dc9d25440
   # [...]
   # {"message": "Processing...", "status": "processing"}

   # [...]

   curl -i -X GET $url/api/v1/requests/dc2b6c27-a849-4787-91d0-df8dc9d25440 -H "Authorization: EmailKey $user_email:$user_key"
   # HTTP/1.1 303 SEE OTHER
   # Location: https://polytope.example.com/api/v1/downloads/default/dc2b6c27-a849-4787-91d0-df8dc9d25440
   # [...]
   # {"contentLength": 51409440, "location": "../downloads/default/dc2b6c27-a849-4787-91d0-df8dc9d25440", "contentType": "application/x-grib"}

Once the data is ready for download, retrieve it via GET to the ``/api/v1/downloads`` endpoint, as pointed to by the ``Location`` header in the latest status poll:

.. code-block:: bash

   curl -X GET https://polytope.example.com/api/v1/downloads/default/dc2b6c27-a849-4787-91d0-df8dc9d25440 -H "Authorization: EmailKey $user_email:$user_key" -o data.grib

The data is ready to use.

Listing requests
----------------

List your active requests via GET to the ``/api/v1/requests`` endpoint:

.. code-block:: bash

   curl -X GET $url/api/v1/requests -H "Authorization: EmailKey $user_email:$user_key" | python3 -m json.tool
   # {
   #     "message": [
   #         {
   #             "id": "dc2b6c27-a849-4787-91d0-df8dc9d25440",
   #             "timestamp": 1635733165.370228,
   #             "last_modified": 1635733171.258691,
   #             "user": {
   #                 "id": "14c3ff0d-ee9c-5583-8ab0-ca71d3801bad",
   #                 "username": "polly",
   #                 "realm": "example",
   #                 "roles": [
   #                     "all"
   #                 ],
   #                 "attributes": {}
   #             },
   #             "verb": "retrieve",
   #             "url": "./downloads/default/dc2b6c27-a849-4787-91d0-df8dc9d25440",
   #             "md5": null,
   #             "collection": "collection1",
   #             "status": "processed",
   #             "user_message": "Success",
   #             "user_request": "{'stream': 'oper', 'levtype': 'sfc', 'param': '165.128/166.128/167.128', 'step': '0', 'time': '00/06/12/18', 'date': '20150323', 'type': 'an', 'class': 'od', 'expver': '0001', 'domain': 'g'}",
   #             "content_length": null
   #         }
   #     ]
   # }

Revoking requests
-----------------

Revoke the request via DELETE to the ``/api/v1/requests/<request-id>`` endpoint:

.. code-block:: bash

   curl -i -X DELETE $url/api/v1/requests/dc2b6c27-a849-4787-91d0-df8dc9d25440 -H "Authorization: EmailKey $user_email:$user_key"
   # HTTP/1.1 200 OK
   # [...]
   # {"message": "Successfully deleted request"}
