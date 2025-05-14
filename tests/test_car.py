import unittest
import logging
import datetime
import json
import os
from pvcontrol.car import (
    Car,
    CarConfig,
    CarData,
    HtmlFormParser,
    LoginFormParser,
    SkodaCar,
    VolkswagenIDCar,
    VolkswagenIDCarConfig,
    SimulatedCar,
)

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
# logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)

# read config file
car_config_file = f"{os.path.dirname(__file__)}/car_test_config.json"
car_config = {}
if os.path.isfile(car_config_file):
    with open(car_config_file, "r") as f:
        car_config = json.load(f)


class HtmlFormParserTest(unittest.TestCase):
    def test_empty(self):
        p = HtmlFormParser("", "")
        self.assertFalse(p.found_form)
        self.assertIsNone(p.action)
        self.assertEqual({}, p.hidden_input_values)

    def test_simple(self):
        p = HtmlFormParser("<form id='id' action='/action'><input type='hidden' id='k' name='k' value='v'/></form>", "id")
        self.assertTrue(p.found_form)
        self.assertEqual("/action", p.action)
        self.assertEqual({"k": "v"}, p.hidden_input_values)

    def test_form_not_found(self):
        p = HtmlFormParser("<form id='id' action='/action'><input type='hidden' id='k' name='k' value='v'/></form>", "id1")
        self.assertFalse(p.found_form)
        self.assertIsNone(p.action)
        self.assertEqual({}, p.hidden_input_values)

    def test_no_action(self):
        p = HtmlFormParser("<form id='id'><input type='hidden' id='k' name='k' value='v'/></form>", "id")
        self.assertTrue(p.found_form)
        self.assertIsNone(p.action)
        self.assertEqual({"k": "v"}, p.hidden_input_values)

    def test_form_multiple(self):
        with self.assertRaises(Exception) as cm:
            HtmlFormParser("<form id='id' action='/action'><input type='hidden' id='k' name='k' value='v'/></form><form id='id'>", "id")
        self.assertIn("Found multiple forms with id=id.", str(cm.exception))

    def test_form_nested(self):
        with self.assertRaises(Exception) as cm:
            HtmlFormParser("<form id='id' action='/action'><input type='hidden' id='k' name='k' value='v'/><form id='id1'></form>", "id")
        self.assertIn("Found nested forms.", str(cm.exception))

    def test_login_form_data(self):
        html = """
<form class="content" id="emailPasswordForm"
      name="emailPasswordForm"
      method="POST"
      novalidate="true"
      action="/signin-service/v1/a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com/login/identifier">
    <div id="title" class="title">
        <div class="primary-title">Welcome</div>
        <div class="sub-title">to We Connect ID.</div>
    </div>
    <input type="hidden" id="csrf" name="_csrf" value="csrf value"/>
    <input type="hidden" id="input_relayState" name="relayState" value="relay state"/>
    <input type="hidden" id="hmac" name="hmac" value="hmac value"/>
    ...
</form>
        """
        p = HtmlFormParser(html, "emailPasswordForm")
        self.assertEqual("/signin-service/v1/a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com/login/identifier", p.action)
        self.assertEqual({"_csrf": "csrf value", "relayState": "relay state", "hmac": "hmac value"}, p.hidden_input_values)


class LoginFormParserTest(unittest.TestCase):
    def test_empty(self):
        p = LoginFormParser("")
        self.assertFalse(p.found_form)
        self.assertEqual({}, p.hidden_input_values)

    def test_simple(self):
        p = LoginFormParser("<script> window._IDK = { p1: 'a',\n p2: \"bbb\"};</script>")
        self.assertTrue(p.found_form)
        self.assertEqual({"p1": "a", "p2": "bbb"}, p.hidden_input_values)

    def test_script_not_found(self):
        p = LoginFormParser("<script>bla</script>")
        self.assertFalse(p.found_form)
        self.assertEqual({}, p.hidden_input_values)

    def test_multiple_script_tags(self):
        p = LoginFormParser("<script>bla</script><script>window._IDK = {p1: 'a',\np2: \"bbb\" }; </script>")
        self.assertTrue(p.found_form)
        self.assertEqual({"p1": "a", "p2": "bbb"}, p.hidden_input_values)

    def test_login_form_data(self):
        html = """
<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/html">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport"
          content="width=device-width, height=device-height, initial-scale=1, maximum-scale=1, user-scalable=no"/>
    <meta name="identitykit" content="loginAuthenticate"/>

    <script type="text/javascript">...</script>
    <script>
        window._IDK = {
            templateModel: {"clientLegalEntityModel":{"clientId":"a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com","clientAppName":"We Connect ID.","clientAppDisplayName":"Volkswagen App","legalEntityInfo":{"name":"Volkswagen","shortName":"VOLKSWAGEN","productName":"Volkswagen ID","theme":"volkswagen_d6","defaultLanguage":"en","termAndConditionsType":"DEFAULT","legalProperties":{"revokeDataContact":"info-datenschutz@volkswagen.de","imprintText":"IMPRINT","countryOfJurisdiction":"DE"}},"informalLanguage":false,"legalEntityCode":"volkswagen","imprintTextKey":"imprint.link.text"},"template":"loginAuthenticate","hmac":"hmac value","useClientRendering":true,"titleKey":"title.login.password","title":null,"emailPasswordForm":{"@class":"com.volkswagen.identitykit.signin.domain.model.dto.EmailPasswordForm","email":"test@gmail.com","password":null},"error":null,"relayState":"12345","nextButtonDisabled":false,"enableNextButtonAfterSeconds":0,"postAction":"login/authenticate","identifierUrl":"login/identifier"},
            disabledFeatures: {
                isFooterEnabled: true,
            },
            currentLocale: 'en',
            csrf_parameterName: '_csrf',
            csrf_token: 'csrf value',
            userSession: {
                userId: '',
                countryOfResidence: ''
            },
            baseUrl: 'https://identity.vwgroup.io',
            consentBaseUrl: 'http://consentapi-service.idk-peu.svc.cluster.local:8080'
        }
    </script>
</head>
<body>
...
</body>
        """
        p = LoginFormParser(html)
        self.assertTrue(p.found_form)
        self.assertEqual("/signin-service/v1/a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com/login/authenticate", p.action)
        self.assertEqual("csrf value", p.hidden_input_values["csrf_token"])
        self.assertEqual("hmac value", p.hidden_input_values["templateModel"]["hmac"])


@unittest.skip
@unittest.skipUnless(len(car_config) > 0, "needs car_test_config.json")
class VolkswagenIDCarTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        cfg = VolkswagenIDCarConfig(**car_config)
        self.car = VolkswagenIDCar(cfg)

    async def test_login_and_refresh_token(self):
        cfg = self.car.get_config()
        client = self.car._login(cfg.user, cfg.password)
        vehicles_res = client.get("https://emea.bff.cariad.digital/vehicle/v1/vehicles")
        self.assertEqual(200, vehicles_res.status_code)
        vehicles = vehicles_res.json()
        print(f"vehicles={vehicles}")
        self.assertEqual(1, len(vehicles))
        # refresh token
        self.car._refresh_token(client)
        vehicles_res = client.get("https://emea.bff.cariad.digital/vehicle/v1/vehicles")
        self.assertEqual(200, vehicles_res.status_code)

    async def test_read_data(self):
        c = await self.car.read_data()
        print(f"car_data={c}")
        self.assertGreater(c.soc, 0)
        self.assertGreater(c.cruising_range, 0)
        self.assertEqual(0, c.error)
        self.assertIsInstance(c.data_captured_at, datetime.datetime)
        self.assertGreater(c.mileage, 0)
        # read second time, no login needed
        c = await self.car.read_data()
        self.assertEqual(0, c.error)
        # invalidate access token -> enforce refresh
        # assert self.car._client is not None
        # assert self.car._client.token is not None
        # self.car._client.token["access_token"] = "xxx"  # doesn't work anymore, leads to 400
        # c = self.car.read_data()
        # self.assertEqual(0, c.error)

    async def test_disabled(self):
        self.car.get_config().disabled = True
        c = await self.car.read_data()
        self.assertEqual(1, c.error)
        self.assertEqual(0, c.soc)


class SimulatedCarTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.car = SimulatedCar(CarConfig())

    async def test_energy_consumption(self):
        c = await self.car.read_data()
        self.assertEqual(50, c.soc)
        self.assertEqual(0, Car._metrics_pvc_car_energy_consumption._value.get())

        # driving
        self.car.set_data(CarData(soc=49))
        c = await self.car.read_data()
        self.assertEqual(49, c.soc)
        self.assertEqual(580, Car._metrics_pvc_car_energy_consumption._value.get())

        self.car.set_data(CarData(soc=40))
        c = await self.car.read_data()
        self.assertEqual(40, c.soc)
        self.assertEqual(5800, Car._metrics_pvc_car_energy_consumption._value.get())

        # not driving
        c = await self.car.read_data()
        self.assertEqual(40, c.soc)
        self.assertEqual(5800, Car._metrics_pvc_car_energy_consumption._value.get())

        # charging
        self.car.set_data(CarData(soc=50))
        c = await self.car.read_data()
        self.assertEqual(50, c.soc)
        self.assertEqual(5800, Car._metrics_pvc_car_energy_consumption._value.get())

        # driving
        self.car.set_data(CarData(soc=40))
        c = await self.car.read_data()
        self.assertEqual(40, c.soc)
        self.assertEqual(2 * 5800, Car._metrics_pvc_car_energy_consumption._value.get())


@unittest.skipUnless(len(car_config) > 0, "needs car_test_config.json")
class SkodaCarTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        cfg = VolkswagenIDCarConfig(**car_config)
        self.car = SkodaCar(cfg)

    async def asyncTearDown(self):
        await self.car.disconnect()

    async def test_read_data(self):
        c = await self.car.read_data()
        print(f"car_data={c}")
        self.assertGreater(c.soc, 0)
        self.assertGreater(c.cruising_range, 0)
        self.assertEqual(0, c.error)
        self.assertIsInstance(c.data_captured_at, datetime.datetime)
        self.assertGreater(c.mileage, 0)

    async def test_disabled(self):
        self.car.get_config().disabled = True
        c = await self.car.read_data()
        self.assertEqual(1, c.error)
        self.assertEqual(0, c.soc)
