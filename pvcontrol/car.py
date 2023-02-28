from dataclasses import dataclass
from datetime import datetime
import json
import re
import dateutil.parser
import logging
import typing
import prometheus_client
from html.parser import HTMLParser
from authlib.oauth2.rfc6749.wrappers import OAuth2Token
from authlib.integrations.requests_client import OAuth2Session
from requests import PreparedRequest, Response
from requests.adapters import BaseAdapter
from requests.exceptions import HTTPError
from pvcontrol.service import BaseConfig, BaseData, BaseService

logger = logging.getLogger(__name__)


@dataclass
class CarData(BaseData):
    data_captured_at: datetime = datetime.min
    soc: float = 0  # [%] state of charge
    cruising_range: int = 0  # [km]


@dataclass
class CarConfig(BaseConfig):
    cycle_time: int = 5 * 60  # [s] cycle time for reading car data, used by scheduler


C = typing.TypeVar("C", bound=CarConfig)  # type of configuration


class Car(BaseService[C, CarData]):
    """Base class / interface for cars"""

    _metrics_pvc_car_soc = prometheus_client.Gauge("pvcontrol_car_soc_ratio", "State of Charge")
    _metrics_pvc_car_range = prometheus_client.Gauge("pvcontrol_car_cruising_range_meters", "Remaining cruising range")

    def __init__(self, config: C):
        super().__init__(config)
        self._set_data(CarData())

    def read_data(self) -> CarData:
        """Read meter data and report metrics. The data is cached."""
        d = self._read_data()
        self._set_data(d)
        Car._metrics_pvc_car_soc.set(d.soc / 100)
        Car._metrics_pvc_car_range.set(d.cruising_range * 1000)
        return d

    def _read_data(self) -> CarData:
        return self.get_data()


class SimulatedCar(Car[CarConfig]):
    def __init__(self, config: CarConfig):
        super().__init__(config)

    def set_data(self, d: CarData):
        self._set_data(d)

    def _read_data(self) -> CarData:
        return CarData(error=0, data_captured_at=datetime.now(), cruising_range=150, soc=50)


# just to permanently grey out car SOC in UI
class NoCar(Car[CarConfig]):
    def __init__(self, config: CarConfig):
        super().__init__(config)
        self.inc_error_counter()
        self.inc_error_counter()
        self.inc_error_counter()
        self.inc_error_counter()

    def _read_data(self) -> CarData:
        return CarData(data_captured_at=datetime.now())


# helper classes for handling authentication
class HtmlFormParser(HTMLParser):
    def __init__(self, html: str, form_id: str):
        super().__init__()
        self.form_id = form_id
        self.hidden_input_values = {}
        self.action = None
        self.found_form = False
        self._processing_form = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "form" and self._processing_form:
            raise Exception("Found nested forms.")
        elif tag == "form" and ("id", self.form_id) in attrs:
            if self.found_form:
                raise Exception(f"Found multiple forms with id={self.form_id}.")
            self.found_form = True
            self._processing_form = True
            actions = [a[1] for a in attrs if a[0] == "action"]
            self.action = actions[0] if len(actions) > 0 else None
        elif self._processing_form and tag == "input" and ("type", "hidden") in attrs:
            name = None
            value = None
            for k, v in attrs:
                if k == "name":
                    name = v
                if k == "value":
                    value = v
            if name is not None:
                self.hidden_input_values[name] = value

    def handle_endtag(self, tag):
        if self._processing_form and tag == "form":
            self._processing_form = False


# parses the login page, not really a form but contains the interesting data in javascript
class LoginFormParser(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.hidden_input_values = {}
        self.found_form = False
        self._processing_script = False
        self.feed(html)
        if "templateModel" in self.hidden_input_values:
            self.action = f"/signin-service/v1/{self.hidden_input_values['templateModel']['clientLegalEntityModel']['clientId']}/{self.hidden_input_values['templateModel']['postAction']}"
        else:
            self.action = ""

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            if self._processing_script:
                raise Exception("Found nested scripts.")
            else:
                self._processing_script = True

    def handle_data(self, data):
        if self._processing_script:
            credPattern = r"\s*window\._IDK\s+=\s+\{(.*)};?\s*"
            match = re.fullmatch(credPattern, data, re.DOTALL)
            if match:
                _json = match.group(1)
                # convert javascript to json
                # single to double quotes (not always correct but good enough)
                _json = _json.replace("'", '"')
                # replace unquoted property names
                # \1 did not work for unknown reasons (python 3.7.10)
                _json = re.sub(r"^\s*(\w+):", '"\g<1>":', _json, 0, re.MULTILINE)  # noqa: W605
                _json = "{" + _json + "}"
                self.hidden_input_values = json.loads(_json)
                self.found_form = True

    def handle_endtag(self, tag):
        if self._processing_script and tag == "script":
            self._processing_script = False


class WeConnectHttpAdapter(BaseAdapter):
    def send(self, request: PreparedRequest, stream=False, timeout=None, verify=True, cert=None, proxies=None) -> Response:
        r = Response()
        r.request = request
        r.status_code = 200
        if request.url is not None:
            r.url = str(request.url)
            r._content = request.url.encode("UTF-8")
        return r

    def close(self):
        pass


@dataclass
class VolkswagenIDCarConfig(CarConfig):
    user: str = ""
    password: str = ""
    vin: str = ""
    timeout: int = 10  # request timeout
    disabled: bool = False


class VolkswagenIDCar(Car[VolkswagenIDCarConfig]):
    mobile_api_uri = "https://emea.bff.cariad.digital/vehicle/v1"

    def __init__(self, config: VolkswagenIDCarConfig):
        super().__init__(config)
        self._client = None
        self._vin = config.vin

    @classmethod
    def _login(cls, user: str, password: str) -> OAuth2Session:
        vw_identity_service_uri = "https://identity.vwgroup.io"
        vwapps_login_service_uri = "https://emea.bff.cariad.digital/user-login"
        client = OAuth2Session(
            client_id="a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com",
            redirect_uri="weconnect://authenticated",
            scope="openid profile badge cars dealers vin",
            nonce="NZ2Q3T6jak0E5pDh",  # TODO: random
        )
        client.session.mount("weconnect://", WeConnectHttpAdapter())
        uri, state = client.create_authorization_url(f"{vwapps_login_service_uri}/v1/authorize", response_type="code id_token token")
        # GET https://login.apps.emea.vwapps.io/authorize?... -> 303
        # GET https://identity.vwgroup.io/oidc/v1/authorize?... -> 302
        # GET https://identity.vwgroup.io/signin-service/v1/signin/a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com?...
        signin_form_response = client.session.get(uri, withhold_token=True)
        signin_form_response.raise_for_status()
        # print(f"response={signin_form_response.text}")
        # returns Email form
        signin_form_parser = HtmlFormParser(signin_form_response.text, "emailPasswordForm")
        if not signin_form_parser.found_form:
            raise Exception("Sign-in form not found.")
        login_params = signin_form_parser.hidden_input_values
        login_params["email"] = user
        # POST https://identity.vwgroup.io/signin-service/v1/a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com/login/identifier -> 303
        # GET https://identity.vwgroup.io/signin-service/v1/a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com/login/authenticate?...
        credential_form_response = client.session.post(
            f"{vw_identity_service_uri}{signin_form_parser.action}", data=login_params, withhold_token=True
        )
        credential_form_response.raise_for_status()
        credential_form_parser = LoginFormParser(credential_form_response.text)
        if not credential_form_parser.found_form:
            raise Exception("Login/Credentials form not found.")
        if "templateModel" not in credential_form_parser.hidden_input_values:
            raise Exception("Login/Credentials form found but doesn't contain necessary data.")
        login_params = {
            "email": user,
            "password": password,
            "hmac": credential_form_parser.hidden_input_values["templateModel"]["hmac"],
            "relayState": credential_form_parser.hidden_input_values["templateModel"]["relayState"],
            "_csrf": credential_form_parser.hidden_input_values["csrf_token"],
        }
        # POST https://identity.vwgroup.io/signin-service/v1/a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com/login/authenticate -> 303
        # if ToS updated
        #   GET https://identity.vwgroup.io/signin-service/v1/a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com/terms-and-conditions?... -> 200
        #   POST https://identity.vwgroup.io/signin-service/v1/a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com/terms-and-conditions -> 302
        # GET https://identity.vwgroup.io/oidc/v1/oauth/sso?clientId=... -> 302
        # GET https://identity.vwgroup.io/signin-service/v1/consent/users/9dcee9cb-e388-42a4-a89b-e12230114e83/a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com?... -> 302
        # GET https://identity.vwgroup.io/oidc/v1/oauth/client/callback/success?... -> 302
        # GET weconnect://authenticated?... -> handled by WeConnectHttpAdapter
        authorization_response = client.session.post(
            f"{vw_identity_service_uri}{credential_form_parser.action}", data=login_params, withhold_token=True
        )
        authorization_response.raise_for_status()
        if "terms-and-conditions" in authorization_response.url:
            logger.info("Updated ToS. Please accept under https://www.volkswagen.de/de/besitzer-und-nutzer/myvolkswagen.html")
            raise Exception("Need to accept ToS")

        token = client.fetch_token(authorization_response=authorization_response.url)
        # print(f"token={token}")
        # fetch the real token
        data = {
            "state": token["state"],
            "id_token": token["id_token"],
            "access_token": token["access_token"],
            "redirect_uri": "weconnect://authenticated",
            "region": "emea",
            "authorizationCode": token["code"],
        }
        # POST https://login.apps.emea.vwapps.io/login/v1
        api_token_response = client.session.post(f"{vwapps_login_service_uri}/login/v1", json=data, withhold_token=True)
        api_token_response.raise_for_status()
        api_token_json = api_token_response.json()
        api_token = OAuth2Token(
            {
                "access_token": api_token_json["accessToken"],
                "refresh_token": api_token_json["refreshToken"],
            }
        )
        # print(f"api_token={api_token}")
        api_client = OAuth2Session(token=api_token, token_endpoint=f"{vwapps_login_service_uri}/refresh/v1")
        return api_client

    @classmethod
    def _refresh_token(cls, client: OAuth2Session):
        token = client.token
        token_endpoint = client.metadata["token_endpoint"]
        refresh_token_response = client.session.get(
            token_endpoint,
            withhold_token=True,
            headers={"Accept": "application/json", "Authorization": f"Bearer {token['refresh_token']}"},
        )
        refresh_token_response.raise_for_status()
        api_token_json = refresh_token_response.json()
        api_token = OAuth2Token(
            {
                "access_token": api_token_json["accessToken"],
                "refresh_token": api_token_json["refreshToken"],
            }
        )
        # print(f"api_token refreshed={api_token}")
        client.token = api_token

    def _read_data(self) -> CarData:
        if self.get_config().disabled:
            self.inc_error_counter()
            return CarData()

        # login if no already done
        try:
            if self._client is None:
                cfg = self.get_config()
                self._client = VolkswagenIDCar._login(cfg.user, cfg.password)

            # TODO: get vin if not configured
            if self._client is not None:
                status_res = self._client.get(f"{VolkswagenIDCar.mobile_api_uri}/vehicles/{self._vin}/selectivestatus?jobs=all")
                if status_res.status_code == 401:
                    # auth error -> refresh token
                    VolkswagenIDCar._refresh_token(self._client)
                    status_res = self._client.get(f"{VolkswagenIDCar.mobile_api_uri}/vehicles/{self._vin}/selectivestatus?jobs=all")
                status_res.raise_for_status()
                status = status_res.json()
                # print(f"{status}")
                range_status = status["fuelStatus"]["rangeStatus"]["value"]
                battery_status = range_status["primaryEngine"]
                self.reset_error_counter()
                return CarData(
                    error=0,
                    data_captured_at=dateutil.parser.isoparse(range_status["carCapturedTimestamp"]),
                    cruising_range=battery_status["remainingRange_km"],
                    soc=battery_status["currentSOC_pct"],
                )
        except HTTPError as e:
            # enforce login on 401
            if e.response.status_code == 401:
                self._client = None
            logger.error(e)
            self.inc_error_counter()
        except Exception as e:
            logger.error(e)
            self.inc_error_counter()

        return self.get_data()


class CarFactory:
    @classmethod
    def newCar(cls, type: str, **kwargs) -> Car:
        if type == "SimulatedCar":
            return SimulatedCar(CarConfig(**kwargs))
        if type == "NoCar":
            return NoCar(CarConfig(**kwargs))
        elif type == "VolkswagenIDCar":
            return VolkswagenIDCar(VolkswagenIDCarConfig(**kwargs))
        else:
            raise ValueError(f"Bad car type: {type}")
