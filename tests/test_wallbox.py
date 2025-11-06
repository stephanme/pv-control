import json
import unittest
from typing import final, override
from unittest.mock import Mock, patch

from pvcontrol.relay import PhaseRelayConfig, SimulatedPhaseRelay
from pvcontrol.wallbox import CarStatus, GoeWallbox, GoeWallboxConfig, WallboxData, WbError

# pyright: reportUninitializedInstanceVariable=false
# pyright: reportPrivateUsage=false


@final
class GoeWallboxTest(unittest.IsolatedAsyncioTestCase):
    @override
    async def asyncSetUp(self) -> None:
        self.relay = SimulatedPhaseRelay(PhaseRelayConfig())
        self.wallbox = GoeWallbox(GoeWallboxConfig(switch_phases_reset_delay=0), self.relay)

    @override
    async def asyncTearDown(self):
        await self.wallbox.close()

    async def test_error_counter(self):
        self.assertEqual(0, self.wallbox.get_error_counter())
        self.wallbox.inc_error_counter()
        self.assertEqual(1, self.wallbox.get_error_counter())
        self.wallbox.reset_error_counter()
        self.assertEqual(0, self.wallbox.get_error_counter())

    def test_json_2_wallbox_data_v3(self):
        # data from new WB
        wb_json = json.loads(
            '{"version":"B","rbc":"251","rbt":"2208867","car":"1","amp":"10","err":"0","ast":"0","alw":"1","stp":"0","cbl":"0","pha":"8","tmp":"30","tma":[10.00,9.0,9.63,9.75,11.50,11.88],"dws":"0","dwo":"0","adi":"1","uby":"0","eto":"120","wst":"3","nrg":[2,0,0,235,0,0,0,0,0,0,0,0,0,0,0,0],"fwv":"020-rc1","sse":"000000","wss":"goe","wke":"","wen":"1","tof":"101","tds":"1","lbr":"255","aho":"2","afi":"8","ama":"32","al1":"11","al2":"12","al3":"15","al4":"24","al5":"31","cid":"255","cch":"65535","cfi":"65280","lse":"0","ust":"0","wak":"","r1x":"2","dto":"0","nmo":"0","eca":"0","ecr":"0","ecd":"0","ec4":"0","ec5":"0","ec6":"0","ec7":"0","ec8":"0","ec9":"0","ec1":"0","rca":"","rcr":"","rcd":"","rc4":"","rc5":"","rc6":"","rc7":"","rc8":"","rc9":"","rc1":"","rna":"","rnm":"","rne":"","rn4":"","rn5":"","rn6":"","rn7":"","rn8":"","rn9":"","rn1":""}'
        )
        wb = self.wallbox._json_2_wallbox_data(wb_json)
        self.assertEqual(WallboxData(0, WbError.OK, CarStatus.NoVehicle, 10, True, 1, 0, 0, 0, 12000, 9.0), wb)
        # phase relay error
        self.relay.set_phases(3)
        wb = self.wallbox._json_2_wallbox_data(wb_json)
        self.assertEqual(WallboxData(0, WbError.PHASE_RELAY_ERR, CarStatus.NoVehicle, 10, True, 1, 0, 0, 0, 12000, 9.0), wb)

    def test_json_2_wallbox_data_v2(self):
        # data from WB
        wb_json = json.loads(
            '{"version":"B","tme":"2812221313","rbc":"93","rbt":"1020214865","car":"4","amp":"6","err":"0","ast":"0","alw":"1","stp":"0","cbl":"32","pha":"8","tmp":"16","dws":"686812","dwo":"0","adi":"0","uby":"0","eto":"95930","wst":"3","txi":"0","nrg":[221,0,0,2,0,0,0,0,0,0,0,0,0,0,0,0],"fwv":"041.0","sse":"005434","wss":"FRITZ!Box7580EO","wke":"********************","wen":"1","cdi":"0","tof":"101","tds":"1","lbr":"20","aho":"3","afi":"7","azo":"1","ama":"32","al1":"10","al2":"16","al3":"20","al4":"24","al5":"32","cid":"255","cch":"65535","cfi":"65280","lse":"1","ust":"0","wak":"ab539ebe51","r1x":"0","dto":"0","nmo":"0","sch":"AAAAAAAAAAAAAAAA","sdp":"0","eca":"0","ecr":"0","ecd":"0","ec4":"0","ec5":"0","ec6":"0","ec7":"0","ec8":"0","ec9":"0","ec1":"0","rca":"B96FBD5A","rcr":"","rcd":"","rc4":"","rc5":"","rc6":"","rc7":"","rc8":"","rc9":"","rc1":"","rna":"","rnm":"","rne":"","rn4":"","rn5":"","rn6":"","rn7":"","rn8":"","rn9":"","rn1":"","loe":0,"lot":0,"lom":0,"lop":0,"log":"","lon":0,"lof":0,"loa":0,"lch":7799,"mce":0,"mcs":"","mcp":0,"mcu":"","mck":"","mcc":0}'
        )
        wb = self.wallbox._json_2_wallbox_data(wb_json)
        self.assertEqual(WallboxData(0, WbError.OK, CarStatus.ChargingFinished, 6, True, 1, 0, 0, 686812 / 360, 9593000, 16.0), wb)
        # phase relay error
        self.relay.set_phases(3)
        wb = self.wallbox._json_2_wallbox_data(wb_json)
        self.assertEqual(
            WallboxData(0, WbError.PHASE_RELAY_ERR, CarStatus.ChargingFinished, 6, True, 1, 0, 0, 686812 / 360, 9593000, 16.0), wb
        )
        # data from WB, charging, bad phases (in 1, out 2)
        wb_json = json.loads(
            '{"version":"B","tme":"1103231603","rbc":"141","rbt":"321094397","car":"2","amp":"6","err":"0","ast":"0","alw":"1","stp":"0","cbl":"32","pha":"11","tmp":"12","dws":"889372","dwo":"0","adi":"0","uby":"0","eto":"100010","wst":"3","txi":"0","nrg":[215,0,0,2,49,0,0,8,0,0,0,85,79,0,0,8],"fwv":"041.0","sse":"005434","wss":"FRITZ!Box7580EO","wke":"********************","wen":"1","cdi":"0","tof":"101","tds":"1","lbr":"20","aho":"3","afi":"7","azo":"1","ama":"32","al1":"10","al2":"16","al3":"20","al4":"24","al5":"32","cid":"255","cch":"65535","cfi":"65280","lse":"1","ust":"0","wak":"ab539ebe51","r1x":"0","dto":"0","nmo":"0","sch":"AAAAAAAAAAAAAAAA","sdp":"0","eca":"0","ecr":"0","ecd":"0","ec4":"0","ec5":"0","ec6":"0","ec7":"0","ec8":"0","ec9":"0","ec1":"0","rca":"B96FBD5A","rcr":"","rcd":"","rc4":"","rc5":"","rc6":"","rc7":"","rc8":"","rc9":"","rc1":"","rna":"","rnm":"","rne":"","rn4":"","rn5":"","rn6":"","rn7":"","rn8":"","rn9":"","rn1":"","loe":0,"lot":0,"lom":0,"lop":0,"log":"","lon":0,"lof":0,"loa":0,"lch":0,"mce":0,"mcs":"","mcp":0,"mcu":"","mck":"","mcc":0}'
        )
        self.relay.set_phases(1)
        wb = self.wallbox._json_2_wallbox_data(wb_json)
        self.assertEqual(WallboxData(0, WbError.OK, CarStatus.Charging, 6, True, 1, 1, 850, 889372 / 360, 10001000, 12.0), wb)

    @patch.object(GoeWallbox, "trigger_reset")
    async def test_set_phases_in(self, mock_trigger_reset: Mock):
        await self.wallbox.set_phases_in(1)
        self.assertEqual(1, self.relay.get_phases())
        mock_trigger_reset.assert_called_with()
        await self.wallbox.set_phases_in(3)
        self.assertEqual(3, self.relay.get_phases())
        mock_trigger_reset.assert_called_with()
        await self.wallbox.set_phases_in(2)
        self.assertEqual(1, self.relay.get_phases())
        mock_trigger_reset.assert_called_with()

    @patch.object(SimulatedPhaseRelay, "set_phases")
    @patch.object(GoeWallbox, "trigger_reset")
    async def test_set_phases_in_error(self, mock_relay_set_phases: Mock, mock_trigger_reset: Mock):
        self.wallbox.inc_error_counter()
        await self.wallbox.set_phases_in(1)
        mock_relay_set_phases.assert_not_called()
        mock_trigger_reset.assert_not_called()

    @patch.object(SimulatedPhaseRelay, "set_phases")
    @patch.object(GoeWallbox, "trigger_reset")
    async def test_set_phases_in_charging(self, mock_relay_set_phases: Mock, mock_trigger_reset: Mock):
        self.wallbox.get_data().phases_out = 3
        await self.wallbox.set_phases_in(1)
        mock_relay_set_phases.assert_not_called()
        mock_trigger_reset.assert_not_called()
