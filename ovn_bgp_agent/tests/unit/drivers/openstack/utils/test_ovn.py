# Copyright 2021 Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from unittest import mock

from ovn_bgp_agent import constants
from ovn_bgp_agent.drivers.openstack.utils import ovn as ovn_utils
from ovn_bgp_agent import exceptions
from ovn_bgp_agent.tests import base as test_base
from ovn_bgp_agent.tests.unit import fakes


class TestOvsdbSbOvnIdl(test_base.TestCase):

    def setUp(self):
        super(TestOvsdbSbOvnIdl, self).setUp()
        self.sb_idl = ovn_utils.OvsdbSbOvnIdl(mock.Mock())

        # Monkey-patch parent class methods
        self.sb_idl.db_find_rows = mock.Mock()
        self.sb_idl.db_list_rows = mock.Mock()

    def test__get_port_by_name(self):
        fake_p_info = 'fake-port-info'
        port = 'fake-port'
        self.sb_idl.db_find_rows.return_value.execute.return_value = [
            fake_p_info]
        ret = self.sb_idl._get_port_by_name(port)

        self.assertEqual(fake_p_info, ret)
        self.sb_idl.db_find_rows.assert_called_once_with(
            'Port_Binding', ('logical_port', '=', port))

    def test__get_port_by_name_empty(self):
        port = 'fake-port'
        self.sb_idl.db_find_rows.return_value.execute.return_value = []
        ret = self.sb_idl._get_port_by_name(port)

        self.assertEqual([], ret)
        self.sb_idl.db_find_rows.assert_called_once_with(
            'Port_Binding', ('logical_port', '=', port))

    def test_get_ports_on_datapath(self):
        dp = 'fake-datapath'
        self.sb_idl.db_find_rows.return_value.execute.return_value = [
            'fake-port']
        ret = self.sb_idl.get_ports_on_datapath(dp)

        self.assertEqual(['fake-port'], ret)
        self.sb_idl.db_find_rows.assert_called_once_with(
            'Port_Binding', ('datapath', '=', dp))

    def test_get_ports_on_datapath_port_type(self):
        dp = 'fake-datapath'
        p_type = 'fake-type'
        self.sb_idl.db_find_rows.return_value.execute.return_value = [
            'fake-port']
        ret = self.sb_idl.get_ports_on_datapath(dp, port_type=p_type)

        self.assertEqual(['fake-port'], ret)
        self.sb_idl.db_find_rows.assert_called_once_with(
            'Port_Binding', ('datapath', '=', dp), ('type', '=', p_type))

    def test_is_provider_network(self):
        dp = 'fake-datapath'
        self.sb_idl.db_find_rows.return_value.execute.return_value = ['fake']
        self.assertTrue(self.sb_idl.is_provider_network(dp))
        self.sb_idl.db_find_rows.assert_called_once_with(
            'Port_Binding', ('datapath', '=', dp),
            ('type', '=', constants.OVN_LOCALNET_VIF_PORT_TYPE))

    def test_is_provider_network_false(self):
        dp = 'fake-datapath'
        self.sb_idl.db_find_rows.return_value.execute.return_value = []
        self.assertFalse(self.sb_idl.is_provider_network(dp))
        self.sb_idl.db_find_rows.assert_called_once_with(
            'Port_Binding', ('datapath', '=', dp),
            ('type', '=', constants.OVN_LOCALNET_VIF_PORT_TYPE))

    def test_get_fip_associated(self):
        port = '1ad5f7e1-fcca-4791-bf50-120c4c73e602'
        datapath = '3e2dc454-6970-4419-9132-b3593d19cdfa'
        fip = '172.24.200.7'
        row = fakes.create_object({
            'datapath': datapath,
            'nat_addresses': ['aa:bb:cc:dd:ee:ff {} is_chassis_resident('
                              '"cr-lrp-{}")'.format(fip, port)]})
        self.sb_idl.db_find_rows.return_value.execute.return_value = [row]
        fip_addr, fip_dp = self.sb_idl.get_fip_associated(port)

        self.assertEqual(fip, fip_addr)
        self.assertEqual(datapath, fip_dp)
        self.sb_idl.db_find_rows.assert_called_once_with(
            'Port_Binding', ('type', '=', constants.OVN_PATCH_VIF_PORT_TYPE))

    def test_get_fip_associated_not_found(self):
        self.sb_idl.db_find_rows.return_value.execute.return_value = []
        fip_addr, fip_dp = self.sb_idl.get_fip_associated('fake-port')

        self.assertIsNone(fip_addr)
        self.assertIsNone(fip_dp)
        self.sb_idl.db_find_rows.assert_called_once_with(
            'Port_Binding', ('type', '=', constants.OVN_PATCH_VIF_PORT_TYPE))

    def _test_is_port_on_chassis(self, should_match=True):
        chassis_name = 'fake-chassis'
        with mock.patch.object(self.sb_idl, '_get_port_by_name') as mock_p:
            ch = fakes.create_object({'name': chassis_name})
            mock_p.return_value = fakes.create_object(
                {'type': constants.OVN_VM_VIF_PORT_TYPE,
                 'chassis': [ch]})
            if should_match:
                self.assertTrue(self.sb_idl.is_port_on_chassis(
                    'fake-port', chassis_name))
            else:
                self.assertFalse(self.sb_idl.is_port_on_chassis(
                    'fake-port', 'wrong-chassis'))

    def test_is_port_on_chassis(self):
        self._test_is_port_on_chassis()

    def test_is_port_on_chassis_no_match_on_chassis(self):
        self._test_is_port_on_chassis(should_match=False)

    def test_is_port_on_chassis_port_not_found(self):
        with mock.patch.object(self.sb_idl, '_get_port_by_name') as mock_p:
            mock_p.return_value = []
            self.assertFalse(self.sb_idl.is_port_on_chassis(
                'fake-port', 'fake-chassis'))

    def _test_is_port_deleted(self, port_exist=True):
        ret_value = mock.Mock() if port_exist else []
        with mock.patch.object(self.sb_idl, '_get_port_by_name') as mock_p:
            mock_p.return_value = ret_value
            if port_exist:
                # Should return False as the port is not deleted
                self.assertFalse(self.sb_idl.is_port_deleted('fake-port'))
            else:
                self.assertTrue(self.sb_idl.is_port_deleted('fake-port'))

    def test_is_port_deleted(self):
        self._test_is_port_deleted()

    def test_is_port_deleted_false(self):
        self._test_is_port_deleted(port_exist=False)

    def test_get_ports_on_chassis(self):
        ch0 = fakes.create_object({'name': 'chassis-0'})
        ch1 = fakes.create_object({'name': 'chassis-1'})
        port0 = fakes.create_object({'name': 'port-0', 'chassis': [ch0]})
        port1 = fakes.create_object({'name': 'port-1', 'chassis': [ch1]})
        port2 = fakes.create_object({'name': 'port-2', 'chassis': [ch0]})
        self.sb_idl.db_list_rows.return_value.execute.return_value = [
            port0, port1, port2]

        ret = self.sb_idl.get_ports_on_chassis('chassis-0')
        self.assertIn(port0, ret)
        self.assertIn(port2, ret)
        # Port-1 is bound to chassis-1
        self.assertNotIn(port1, ret)

    def _test_get_network_name_and_tag(self, network_in_bridge_map=True):
        tag = 1001
        network = 'public' if network_in_bridge_map else 'spongebob'
        with mock.patch.object(self.sb_idl, 'get_ports_on_datapath') as m_dp:
            row = fakes.create_object({
                'options': {'network_name': network},
                'tag': tag})
            m_dp.return_value = [row, ]
            net_name, net_tag = self.sb_idl.get_network_name_and_tag(
                'fake-dp', 'br-ex:public'.format(network))

            if network_in_bridge_map:
                self.assertEqual(network, net_name)
                self.assertEqual(tag, net_tag)
            else:
                self.assertIsNone(net_name)
                self.assertIsNone(net_tag)

    def test_get_network_name_and_tag(self):
        self._test_get_network_name_and_tag()

    def test_get_network_name_and_tag_not_in_bridge_mappings(self):
        self._test_get_network_name_and_tag(network_in_bridge_map=False)

    def _test_get_network_vlan_tag_by_network_name(self, match=True):
        network = 'public' if match else 'spongebob'
        tag = 1001
        row = fakes.create_object({
            'options': {'network_name': 'public'},
            'tag': tag})
        self.sb_idl.db_find_rows.return_value.execute.return_value = [row, ]

        ret = self.sb_idl.get_network_vlan_tag_by_network_name(network)
        if match:
            self.assertEqual(tag, ret)
        else:
            self.assertIsNone(ret)

    def test_get_network_vlan_tag_by_network_name(self):
        self._test_get_network_vlan_tag_by_network_name()

    def test_get_network_vlan_tag_by_network_name_no_match(self):
        self._test_get_network_vlan_tag_by_network_name(match=False)

    def _test_is_router_gateway_on_chassis(self, match=True):
        chassis = 'chassis-0' if match else 'spongebob'
        port = '39c38ce6-f0ea-484e-a57c-aec0d4e961a5'
        with mock.patch.object(self.sb_idl, 'get_ports_on_datapath') as m_dp:
            ch = fakes.create_object({'name': 'chassis-0'})
            row = fakes.create_object({'logical_port': port, 'chassis': [ch]})
            m_dp.return_value = [row, ]
            ret = self.sb_idl.is_router_gateway_on_chassis('fake-dp', chassis)

            if match:
                self.assertEqual(port, ret)
            else:
                self.assertIsNone(ret)

    def test_is_router_gateway_on_chassis(self):
        self._test_is_router_gateway_on_chassis()

    def test_is_router_gateway_on_chassis_not_on_chassis(self):
        self._test_is_router_gateway_on_chassis(match=False)

    def _test_get_lrp_port_for_datapath(self, has_options=True):
        peer = '75c793bd-d865-48f3-8f05-68ba4239d14e'
        with mock.patch.object(self.sb_idl, 'get_ports_on_datapath') as m_dp:
            options = {}
            if has_options:
                options.update({'peer': peer})
            row = fakes.create_object({'options': options})
            m_dp.return_value = [row, ]
            ret = self.sb_idl.get_lrp_port_for_datapath('fake-dp')

            if has_options:
                self.assertEqual(peer, ret)
            else:
                self.assertIsNone(ret)

    def test_get_lrp_port_for_datapath(self):
        self._test_get_lrp_port_for_datapath()

    def test_get_lrp_port_for_datapath_no_options(self):
        self._test_get_lrp_port_for_datapath(has_options=False)

    def _test_get_port_datapath(self, port_found=True):
        dp = '3fce2c5f-7801-469b-894e-05561e3bda15'
        with mock.patch.object(self.sb_idl, '_get_port_by_name') as mock_p:
            port_info = None
            if port_found:
                port_info = fakes.create_object({'datapath': dp})
            mock_p.return_value = port_info
            ret = self.sb_idl.get_port_datapath('fake-port')

            if port_found:
                self.assertEqual(dp, ret)
            else:
                self.assertIsNone(ret)

    def test_get_port_datapath(self):
        self._test_get_port_datapath()

    def test_get_port_datapath_port_not_found(self):
        self._test_get_port_datapath(port_found=False)

    def test_get_ip_from_port_peer(self):
        ip = '172.24.200.7'
        port = fakes.create_object({'options': {'peer': 'fake-peer'}})
        with mock.patch.object(self.sb_idl, '_get_port_by_name') as mock_p:
            port_peer = fakes.create_object({
                'mac': ['aa:bb:cc:dd:ee:ff 172.24.200.7']})
            mock_p.return_value = port_peer
            ret = self.sb_idl.get_ip_from_port_peer(port)

            self.assertEqual(ip, ret)

    def test_get_ip_from_port_peer_port_not_found(self):
        port = fakes.create_object({'options': {'peer': 'fake-peer'}})
        with mock.patch.object(self.sb_idl, '_get_port_by_name') as mock_p:
            mock_p.return_value = []

            self.assertRaises(exceptions.PortNotFound,
                              self.sb_idl.get_ip_from_port_peer, port)

    def _test_get_evpn_info_from_port_name(self, crlrp=False, lrp=False):
        port = '48dc4289-a1b9-4505-b513-4eff0c460c29'
        if crlrp:
            port_name = constants.OVN_CRLRP_PORT_NAME_PREFIX + port
        elif lrp:
            port_name = constants.OVN_LRP_PORT_NAME_PREFIX + port
        else:
            port_name = port

        expected_return = 'spongebob'
        with mock.patch.object(self.sb_idl, '_get_port_by_name') as mock_p:
            with mock.patch.object(self.sb_idl, 'get_evpn_info') as mock_evpn:
                mock_evpn.return_value = expected_return
                ret = self.sb_idl.get_evpn_info_from_port_name(port_name)

                mock_p.assert_called_once_with(port)
                self.assertEqual(expected_return, ret)

    def test_get_evpn_info_from_port_name(self):
        self._test_get_evpn_info_from_port_name()

    def test_get_evpn_info_from_port_name_crlrp(self):
        self._test_get_evpn_info_from_port_name(crlrp=True)

    def test_get_evpn_info_from_port_name_lrp(self):
        self._test_get_evpn_info_from_port_name(lrp=True)

    def _test_get_evpn_info(self, value_error=False):
        vni = 'invalid-vni' if value_error else '1001'
        port = fakes.create_object({
            'name': 'fake-port',
            'external_ids': {constants.OVN_EVPN_VNI_EXT_ID_KEY: vni,
                             constants.OVN_EVPN_AS_EXT_ID_KEY: '123'}})
        ret = self.sb_idl.get_evpn_info(port)

        expected_return = {}
        if not value_error:
            expected_return.update({'vni': 1001, 'bgp_as': 123})

        self.assertEqual(expected_return, ret)

    def test_get_evpn_info(self):
        self._test_get_evpn_info()

    def test_get_evpn_info_value_error(self):
        self._test_get_evpn_info(value_error=True)

    def test_get_evpn_info_key_error(self):
        port = fakes.create_object({'name': 'fake-port', 'external_ids': {}})
        ret = self.sb_idl.get_evpn_info(port)
        self.assertEqual({}, ret)

    def _test_get_port_if_local_chassis(self, wrong_chassis=False):
        chassis = 'wrong-chassis' if wrong_chassis else 'chassis-0'
        with mock.patch.object(self.sb_idl, '_get_port_by_name') as mock_p:
            ch = fakes.create_object({'name': 'chassis-0'})
            port = fakes.create_object({'chassis': [ch]})
            mock_p.return_value = port
            ret = self.sb_idl.get_port_if_local_chassis('fake-port', chassis)

            if wrong_chassis:
                self.assertIsNone(ret)
            else:
                self.assertEqual(port, ret)

    def test_get_port_if_local_chassis(self):
        self._test_get_port_if_local_chassis()

    def test_get_port_if_local_chassis_wrong_chassis(self):
        self._test_get_port_if_local_chassis(wrong_chassis=True)