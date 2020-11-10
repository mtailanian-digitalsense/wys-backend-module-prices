# API Endpoints for Prices

Port: 8088

## Upload Excel to Add/Update Costs

**URL**: `/api/prices/upload`

**Method**: `POST`

**Auth Required**: YES

**Body**

Multipart file

### Success Response

**Code** : `201 Created`

## Error Responses

**Condition** : If body is invalid

**Code** : `400 Bad Request`

**Content** : `{error_message}`

### Or

**Condition** :  If server or database has some error.

**Code** : `500 Internal Error Server`

**Content** : `{error_message}`

## Get all information needed to display in frontend

**URL**: `/api/prices/create`

**Method**: `GET`

**Auth Required**: YES

### Success Response

**Code** : `200 OK`

### Error Responses

**Condition** :  If server or database has some error.

**Code** : `500 Internal Error Server`

**Content** : `{error_message}`

## Get Estimated Price

**URL**: `/api/prices`

**Method**: `POST`

**Auth Required**: YES

**Body**

````json
{
  "categories": [
    {
      "code": "string", // Category Code
      "id": 0, // category id
      "name": "string", // Category name
      "resp": "low", // Response ("low", "normal", "high")
      "type": "string" // Type of question ("A" or "B")
    }
  ],
  "country": "string",
  "workspaces": [
    {
      "id": 0, // workspace id
      "m2_gen_id": 0, // m2 gen id
      "observation": 0, // observation
      "quantity": 0, // quantity
      "space_id": 0 // space ID
    }
  ]
}

````
### Success Response

**Code** : `200 OK`

````json
{'value': final_value}
````

## Error Responses

**Condition** : If body is invalid

**Code** : `400 Bad Request`

**Content** : `{error_message}`

### Or

**Condition** :  If server or database has some error.

**Code** : `500 Internal Error Server`

**Content** : `{error_message}`
