import unittest
import os
from http import HTTPStatus
from io import BytesIO

import jwt
from main import PriceGen, PriceValue, \
    PriceCategory, PriceCountry, PriceModule, \
    db, app


class MyTestCase(unittest.TestCase):
    def setUp(self):
        db.session.remove()
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + \
                                                os.path.join('.', 'test.db')
        self.app = app.test_client()
        f = open('oauth-private.key', 'r')
        self.key = f.read()
        f.close()

    @staticmethod
    def build_token(key, user_id=1):
        payload = {
            "aud": "1",
            "jti": "450ca670aff83b220d8fd58d9584365614fceaf210c8db2cf4754864318b5a398cf625071993680d",
            "iat": 1592309117,
            "nbf": 1592309117,
            "exp": 1624225038,
            "sub": "23",
            "user_id": user_id,
            "scopes": [],
            "uid": 23
        }
        return ('Bearer ' + jwt.encode(payload,
                                       key,
                                       algorithm='RS256')
                .decode('utf-8')).encode('utf-8')

    def testDBCreate(self):
        db.create_all()
        db.session.commit()
        print("---- DB is OK ----")


    def test_add_file(self):
        db.create_all()
        db.session.commit()
        with app.test_client() as client:
            with open('Template_Planilla_Costos.xlsx', 'rb') as test_file:
                client.environ_base['HTTP_AUTHORIZATION'] = self.build_token(self.key)
                files = {'file': (BytesIO(test_file.read()), 'planilla_excel.xlsx')}

                rv = client.post('/api/prices/',
                                 data=files,
                                 follow_redirects=True,
                                 content_type='multipart/form-data')
                test_file.close()
                self.assertEqual(rv.status_code, HTTPStatus.OK)
                return rv

    def test_categories(self):
        db.create_all()
        db.session.commit()
        with app.test_client() as client:
            with open('Template_Planilla_Costos.xlsx', 'rb') as test_file:
                client.environ_base['HTTP_AUTHORIZATION'] = self.build_token(self.key)
                files = {'file': (BytesIO(test_file.read()), 'planilla_excel.xlsx')}

                rv = client.post('/api/prices/',
                                 data=files,
                                 follow_redirects=True,
                                 content_type='multipart/form-data')
                test_file.close()
            self.assertEqual(rv.status_code, HTTPStatus.OK)

            rv = client.get('/api/prices/categories')
            self.assertEqual(rv.status_code, HTTPStatus.OK)



    def tearDown(self):
        db.session.remove()
        db.drop_all()