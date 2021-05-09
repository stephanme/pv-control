import unittest
from unittest.mock import patch
import json

from pvcontrol.wallbox import CarStatus, GoeWallbox, GoeWallboxConfig, WallboxData, WbError


class GoeWallboxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.wallbox = GoeWallbox(GoeWallboxConfig())

    def test_error_counter(self):
        self.assertEqual(0, self.wallbox.get_error_counter())
        self.wallbox.inc_error_counter()
        self.assertEqual(1, self.wallbox.get_error_counter())
        self.wallbox.reset_error_counter()
        self.assertEqual(0, self.wallbox.get_error_counter())

    def test_json_2_wallbox_data(self):
        # data from new WB
        wb_json = json.loads(
            '{"version":"B","rbc":"251","rbt":"2208867","car":"1","amp":"10","err":"0","ast":"0","alw":"1","stp":"0","cbl":"0","pha":"8","tmp":"30","dws":"0","dwo":"0","adi":"1","uby":"0","eto":"120","wst":"3","nrg":[2,0,0,235,0,0,0,0,0,0,0,0,0,0,0,0],"fwv":"020-rc1","sse":"000000","wss":"goe","wke":"","wen":"1","tof":"101","tds":"1","lbr":"255","aho":"2","afi":"8","ama":"32","al1":"11","al2":"12","al3":"15","al4":"24","al5":"31","cid":"255","cch":"65535","cfi":"65280","lse":"0","ust":"0","wak":"","r1x":"2","dto":"0","nmo":"0","eca":"0","ecr":"0","ecd":"0","ec4":"0","ec5":"0","ec6":"0","ec7":"0","ec8":"0","ec9":"0","ec1":"0","rca":"","rcr":"","rcd":"","rc4":"","rc5":"","rc6":"","rc7":"","rc8":"","rc9":"","rc1":"","rna":"","rnm":"","rne":"","rn4":"","rn5":"","rn6":"","rn7":"","rn8":"","rn9":"","rn1":""}'
        )
        wb = GoeWallbox._json_2_wallbox_data(wb_json)
        self.assertEqual(WallboxData(0, WbError.OK, CarStatus.NoVehicle, 10, True, 1, 0, 0, 0, 12000), wb)

    @patch("pvcontrol.relay.writeChannel1")
    def test_set_phases_in(self, mock_writeChannel1):
        self.wallbox.set_phases_in(1)
        mock_writeChannel1.assert_called_with(True)
        self.wallbox.set_phases_in(3)
        mock_writeChannel1.assert_called_with(False)
        self.wallbox.set_phases_in(2)
        mock_writeChannel1.assert_called_with(False)

    @patch("pvcontrol.relay.writeChannel1")
    def test_set_phases_in_error(self, mock_writeChannel1):
        self.wallbox.inc_error_counter()
        self.wallbox.set_phases_in(1)
        mock_writeChannel1.assert_not_called()

    @patch("pvcontrol.relay.writeChannel1")
    def test_set_phases_in_charging(self, mock_writeChannel1):
        self.wallbox.get_data().phases_out = 3
        self.wallbox.set_phases_in(1)
        mock_writeChannel1.assert_not_called()
