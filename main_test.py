import unittest
import os
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

        db.create_all()
        db.session.commit()
        print("---- DB is OK ----")

    def testDBCreate(self):
        print("---- DB is OK ----")

    def tearDown(self):
        db.session.remove()
        db.drop_all()