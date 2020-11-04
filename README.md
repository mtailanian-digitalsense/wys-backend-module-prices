# API Endpoints for Prices

Port: 8088

## Upload Excel to Add/Update Costs

**URL**: `/api/prices/`

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
