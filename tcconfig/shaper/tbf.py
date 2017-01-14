# encoding: utf-8

"""
.. codeauthor:: Tsuyoshi Hombashi <gogogo.vm@gmail.com>
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import dataproperty
from subprocrunner import SubprocessRunner

from .._common import (
    ANYWHERE_NETWORK,
    run_command_helper,
)
from .._error import (
    EmptyParameterError,
)
from .._iptables import (
    IptablesMangleController,
)
from ._interface import AbstractShaper


class TbfShaper(AbstractShaper):

    __MIN_BUFFER_BYTE = 1600

    __FILTER_IPTABLES_MARK_ID_OFFSET = 100

    @property
    def algorithm_name(self):
        return "tbf"

    def make_qdisc(self):
        command = " ".join([
            "tc qdisc add",
            self.dev,
            "root",
            "handle {:s}:".format(self._tc_obj.qdisc_major_id_str),
            "prio",
        ])

        return run_command_helper(
            command,
            self._tc_obj.REGEXP_FILE_EXISTS,
            self._tc_obj.EXISTS_MSG_TEMPLATE.format(
                "failed to add qdisc: prio qdisc already exists."))

    def add_rate(self):
        try:
            self._tc_obj.validate_bandwidth_rate()
        except EmptyParameterError:
            return 0

        command_list = [
            "tc qdisc add",
            self.dev,
            "parent {:x}:{:d}".format(
                self._tc_obj.get_netem_qdisc_major_id(
                    self._tc_obj.qdisc_major_id),
                self._tc_obj.get_qdisc_minor_id()),
            "handle 20:",
            self.algorithm_name,
            "rate {:f}kbit".format(self._tc_obj.bandwidth_rate),
            "buffer {:d}".format(
                max(int(self._tc_obj.bandwidth_rate), self.__MIN_BUFFER_BYTE)
            ),  # [byte]
            "limit 10000",
        ]

        return SubprocessRunner(" ".join(command_list)).run()

    def add_filter(self):
        self.__set_pre_network_filter()

        command_list = [
            "tc filter add",
            self.dev,
            "protocol ip",
            "parent {:s}:".format(self._tc_obj.qdisc_major_id_str),
            "prio 1",
        ]

        if self._tc_obj.is_use_iptables():
            mark_id = (
                IptablesMangleController.get_unique_mark_id() +
                self.__FILTER_IPTABLES_MARK_ID_OFFSET)
            command_list.append("handle {:d} fw".format(mark_id))

            self._tc_obj.add_mangle_mark(mark_id)
        else:
            if all([
                dataproperty.is_empty_string(self._tc_obj.network),
                self._tc_obj.port is None,
            ]):
                return 0

            command_list.append("u32")
            if dataproperty.is_not_empty_string(self._tc_obj.network):
                command_list.append("match ip {:s} {:s}".format(
                    self._tc_obj.get_network_direction_str(),
                    self._tc_obj.network))
            if self._tc_obj.port is not None:
                command_list.append(
                    "match ip dport {:d} 0xffff".format(self._tc_obj.port))

        command_list.append("flowid {:s}:{:d}".format(
            self._tc_obj.qdisc_major_id_str,
            self._tc_obj.get_qdisc_minor_id()))

        return SubprocessRunner(" ".join(command_list)).run()

    def __set_pre_network_filter(self):
        if self._tc_obj.is_use_iptables():
            return 0

        if all([
            dataproperty.is_empty_string(self._tc_obj.network),
            not dataproperty.IntegerType(self._tc_obj.port).is_type(),
        ]):
            flowid = "{:s}:{:d}".format(
                self._tc_obj.qdisc_major_id_str,
                self._tc_obj.get_qdisc_minor_id())
        else:
            flowid = "{:s}:2".format(self._tc_obj.qdisc_major_id_str)

        command = " ".join([
            "tc filter add",
            self.dev,
            "protocol ip",
            "parent {:s}:".format(self._tc_obj.qdisc_major_id_str),
            "prio 2 u32 match ip {:s} {:s}".format(
                self._tc_obj.get_network_direction_str(),
                ANYWHERE_NETWORK),
            "flowid {:s}".format(flowid),
        ])

        return SubprocessRunner(command).run()