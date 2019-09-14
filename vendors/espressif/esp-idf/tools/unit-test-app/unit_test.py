"""
Test script for unit test case.
"""

import re
import os
import sys
import time
import threading

# if we want to run test case outside `tiny-test-fw` folder,
# we need to insert tiny-test-fw path into sys path
test_fw_path = os.getenv("TEST_FW_PATH")
if test_fw_path and test_fw_path not in sys.path:
    sys.path.insert(0, test_fw_path)

import TinyFW
import IDF
import Utility
from DUT import ExpectTimeout
from IDF.IDFApp import UT


UT_APP_BOOT_UP_DONE = "Press ENTER to see the list of tests."
RESET_PATTERN = re.compile(r"(ets [\w]{3}\s+[\d]{1,2} [\d]{4} [\d]{2}:[\d]{2}:[\d]{2}[^()]*\([\w].*?\))")
EXCEPTION_PATTERN = re.compile(r"(Guru Meditation Error: Core\s+\d panic'ed \([\w].*?\))")
ABORT_PATTERN = re.compile(r"(abort\(\) was called at PC 0x[a-eA-E\d]{8} on core \d)")
FINISH_PATTERN = re.compile(r"1 Tests (\d) Failures (\d) Ignored")

STARTUP_TIMEOUT = 10
DUT_STARTUP_CHECK_RETRY_COUNT = 5
TEST_HISTORY_CHECK_TIMEOUT = 1


def format_test_case_config(test_case_data):
    """
    convert the test case data to unified format.
    We need to following info to run unit test cases:

    1. unit test app config
    2. test case name
    3. test case reset info

    the formatted case config is a dict, with ut app config as keys. The value is a list of test cases.
    Each test case is a dict with "name" and "reset" as keys. For example::

    case_config = {
        "default": [{"name": "restart from PRO CPU", "reset": "SW_CPU_RESET"}, {...}],
        "psram": [{"name": "restart from PRO CPU", "reset": "SW_CPU_RESET"}],
    }

    If config is not specified for test case, then

    :param test_case_data: string, list, or a dictionary list
    :return: formatted data
    """

    case_config = dict()

    def parse_case(one_case_data):
        """ parse and format one case """

        def process_reset_list(reset_list):
            # strip space and remove white space only items
            _output = list()
            for _r in reset_list:
                _data = _r.strip(" ")
                if _data:
                    _output.append(_data)
            return _output

        _case = dict()
        if isinstance(one_case_data, str):
            _temp = one_case_data.split(" [reset=")
            _case["name"] = _temp[0]
            try:
                _case["reset"] = process_reset_list(_temp[1][0:-1].split(","))
            except IndexError:
                _case["reset"] = list()
        elif isinstance(one_case_data, dict):
            _case = one_case_data.copy()
            assert "name" in _case
            if "reset" not in _case:
                _case["reset"] = list()
            else:
                if isinstance(_case["reset"], str):
                    _case["reset"] = process_reset_list(_case["reset"].split(","))
        else:
            raise TypeError("Not supported type during parsing unit test case")

        if "config" not in _case:
            _case["config"] = "default"

        return _case

    if not isinstance(test_case_data, list):
        test_case_data = [test_case_data]

    for case_data in test_case_data:
        parsed_case = parse_case(case_data)
        try:
            case_config[parsed_case["config"]].append(parsed_case)
        except KeyError:
            case_config[parsed_case["config"]] = [parsed_case]

    return case_config


def replace_app_bin(dut, name, new_app_bin):
    if new_app_bin is None:
        return
    search_pattern = '/{}.bin'.format(name)
    for i, config in enumerate(dut.download_config):
        if config.endswith(search_pattern):
            dut.download_config[i] = new_app_bin
            Utility.console_log("The replaced application binary is {}".format(new_app_bin), "O")
            break


def reset_dut(dut):
    dut.reset()
    # esptool ``run`` cmd takes quite long time.
    # before reset finish, serial port is closed. therefore DUT could already bootup before serial port opened.
    # this could cause checking bootup print failed.
    # now use input cmd `-` and check test history to check if DUT is bootup.
    # we'll retry this step for a few times in case `dut.reset` returns during DUT bootup (when DUT can't process any command).
    for _ in range(DUT_STARTUP_CHECK_RETRY_COUNT):
        dut.write("-")
        try:
            dut.expect("0 Tests 0 Failures 0 Ignored", timeout=TEST_HISTORY_CHECK_TIMEOUT)
            break
        except ExpectTimeout:
            pass
    else:
        raise AssertionError("Reset {} ({}) failed!".format(dut.name, dut.port))


def run_one_normal_case(dut, one_case, junit_test_case, failed_cases):

    reset_dut(dut)

    dut.start_capture_raw_data()
    # run test case
    dut.write("\"{}\"".format(one_case["name"]))
    dut.expect("Running " + one_case["name"] + "...")

    exception_reset_list = []

    # we want to set this flag in callbacks (inner functions)
    # use list here so we can use append to set this flag
    test_finish = list()

    # expect callbacks
    def one_case_finish(result):
        """ one test finished, let expect loop break and log result """
        test_finish.append(True)
        output = dut.stop_capture_raw_data()
        if result:
            Utility.console_log("Success: " + one_case["name"], color="green")
        else:
            failed_cases.append(one_case["name"])
            Utility.console_log("Failed: " + one_case["name"], color="red")
            junit_test_case.add_failure_info(output)

    def handle_exception_reset(data):
        """
        just append data to exception list.
        exception list will be checked in ``handle_reset_finish``, once reset finished.
        """
        exception_reset_list.append(data[0])

    def handle_test_finish(data):
        """ test finished without reset """
        # in this scenario reset should not happen
        assert not exception_reset_list
        if int(data[1]):
            # case ignored
            Utility.console_log("Ignored: " + one_case["name"], color="orange")
            junit_test_case.add_skipped_info("ignored")
        one_case_finish(not int(data[0]))

    def handle_reset_finish(data):
        """ reset happened and reboot finished """
        assert exception_reset_list  # reboot but no exception/reset logged. should never happen
        result = False
        if len(one_case["reset"]) == len(exception_reset_list):
            for i, exception in enumerate(exception_reset_list):
                if one_case["reset"][i] not in exception:
                    break
            else:
                result = True
        if not result:
            err_msg = "Reset Check Failed: \r\n\tExpected: {}\r\n\tGet: {}".format(one_case["reset"],
                                                                                   exception_reset_list)
            Utility.console_log(err_msg, color="orange")
            junit_test_case.add_error_info(err_msg)
        one_case_finish(result)

    while not test_finish:
        try:
            dut.expect_any((RESET_PATTERN, handle_exception_reset),
                           (EXCEPTION_PATTERN, handle_exception_reset),
                           (ABORT_PATTERN, handle_exception_reset),
                           (FINISH_PATTERN, handle_test_finish),
                           (UT_APP_BOOT_UP_DONE, handle_reset_finish),
                           timeout=one_case["timeout"])
        except ExpectTimeout:
            Utility.console_log("Timeout in expect", color="orange")
            junit_test_case.add_error_info("timeout")
            one_case_finish(False)
            break


@IDF.idf_unit_test(env_tag="UT_T1_1", junit_report_by_case=True)
def run_unit_test_cases(env, extra_data):
    """
    extra_data can be three types of value
    1. as string:
               1. "case_name"
               2. "case_name [reset=RESET_REASON]"
    2. as dict:
               1. with key like {"name": "Intr_alloc test, shared ints"}
               2. with key like {"name": "restart from PRO CPU", "reset": "SW_CPU_RESET", "config": "psram"}
    3. as list of string or dict:
               [case1, case2, case3, {"name": "restart from PRO CPU", "reset": "SW_CPU_RESET"}, ...]

    :param extra_data: the case name or case list or case dictionary
    :return: None
    """

    case_config = format_test_case_config(extra_data)

    # we don't want stop on failed case (unless some special scenarios we can't handle)
    # this flag is used to log if any of the case failed during executing
    # Before exit test function this flag is used to log if the case fails
    failed_cases = []

    for ut_config in case_config:
        Utility.console_log("Running unit test for config: " + ut_config, "O")
        dut = env.get_dut("unit-test-app", app_path=ut_config, allow_dut_exception=True)
        dut.start_app()
        Utility.console_log("Download finished, start running test cases", "O")

        for one_case in case_config[ut_config]:
            # create junit report test case
            junit_test_case = TinyFW.JunitReport.create_test_case("[{}] {}".format(ut_config, one_case["name"]))
            try:
                run_one_normal_case(dut, one_case, junit_test_case, failed_cases)
            except Exception as e:
                junit_test_case.add_failure_info("Unexpected exception: " + str(e))
                failed_cases.append(one_case["name"])
            finally:
                TinyFW.JunitReport.test_case_finish(junit_test_case)

    # raise exception if any case fails
    if failed_cases:
        Utility.console_log("Failed Cases:", color="red")
        for _case_name in failed_cases:
            Utility.console_log("\t" + _case_name, color="red")
        raise AssertionError("Unit Test Failed")


class Handler(threading.Thread):

    WAIT_SIGNAL_PATTERN = re.compile(r'Waiting for signal: \[(.+)\]!')
    SEND_SIGNAL_PATTERN = re.compile(r'Send signal: \[(.+)\]!')
    FINISH_PATTERN = re.compile(r"1 Tests (\d) Failures (\d) Ignored")

    def __init__(self, dut, sent_signal_list, lock, parent_case_name, child_case_index, timeout):
        self.dut = dut
        self.sent_signal_list = sent_signal_list
        self.lock = lock
        self.parent_case_name = parent_case_name
        self.child_case_name = ""
        self.child_case_index = child_case_index + 1
        self.finish = False
        self.result = False
        self.output = ""
        self.fail_name = None
        self.timeout = timeout
        self.force_stop = threading.Event()  # it show the running status

        reset_dut(self.dut)  # reset the board to make it start from begining

        threading.Thread.__init__(self, name="{} Handler".format(dut))

    def run(self):

        self.dut.start_capture_raw_data()

        def get_child_case_name(data):
            self.child_case_name = data[0]
            time.sleep(1)
            self.dut.write(str(self.child_case_index))

        def one_device_case_finish(result):
            """ one test finished, let expect loop break and log result """
            self.finish = True
            self.result = result
            self.output = "[{}]\n\n{}\n".format(self.child_case_name,
                                                self.dut.stop_capture_raw_data())
            if not result:
                self.fail_name = self.child_case_name

        def device_wait_action(data):
            start_time = time.time()
            expected_signal = data[0]
            while 1:
                if time.time() > start_time + self.timeout:
                    Utility.console_log("Timeout in device for function: %s"%self.child_case_name, color="orange")
                    break
                with self.lock:
                    if expected_signal in self.sent_signal_list:
                        self.dut.write(" ")
                        self.sent_signal_list.remove(expected_signal)
                        break
                time.sleep(0.01)

        def device_send_action(data):
            with self.lock:
                self.sent_signal_list.append(data[0].encode('utf-8'))

        def handle_device_test_finish(data):
            """ test finished without reset """
            # in this scenario reset should not happen
            if int(data[1]):
                # case ignored
                Utility.console_log("Ignored: " + self.child_case_name, color="orange")
            one_device_case_finish(not int(data[0]))

        try:
            time.sleep(1)
            self.dut.write("\"{}\"".format(self.parent_case_name))
            self.dut.expect("Running " + self.parent_case_name + "...")
        except ExpectTimeout:
            Utility.console_log("No case detected!", color="orange")
        while not self.finish and not self.force_stop.isSet():
            try:
                self.dut.expect_any((re.compile('\(' + str(self.child_case_index) + '\)\s"(\w+)"'), get_child_case_name),
                                    (self.WAIT_SIGNAL_PATTERN, device_wait_action),  # wait signal pattern
                                    (self.SEND_SIGNAL_PATTERN, device_send_action),  # send signal pattern
                                    (self.FINISH_PATTERN, handle_device_test_finish),  # test finish pattern
                                    timeout=self.timeout)
            except ExpectTimeout:
                Utility.console_log("Timeout in expect", color="orange")
                one_device_case_finish(False)
                break

    def stop(self):
        self.force_stop.set()


def get_case_info(one_case):
    parent_case = one_case["name"]
    child_case_num = one_case["child case num"]
    return parent_case, child_case_num


def get_dut(duts, env, name, ut_config):
    if name in duts:
        dut = duts[name]
    else:
        dut = env.get_dut(name, app_path=ut_config, allow_dut_exception=True)
        duts[name] = dut
        dut.start_app()
    return dut


def run_one_multiple_devices_case(duts, ut_config, env, one_case, junit_test_case):
    lock = threading.RLock()
    threads = []
    send_signal_list = []
    result = True
    parent_case, case_num = get_case_info(one_case)

    for i in range(case_num):
        dut = get_dut(duts, env, "dut%d" % i, ut_config)
        threads.append(Handler(dut, send_signal_list, lock,
                               parent_case, i, one_case["timeout"]))
    for thread in threads:
        thread.setDaemon(True)
        thread.start()
    output = "Multiple Device Failed\n"
    for thread in threads:
        thread.join()
        result = result and thread.result
        output += thread.output
        if not thread.result:
            [thd.stop() for thd in threads]

    if not result:
        junit_test_case.add_failure_info(output)
    return result


@IDF.idf_unit_test(env_tag="UT_T2_1", junit_report_by_case=True)
def run_multiple_devices_cases(env, extra_data):
    """
     extra_data can be two types of value
     1. as dict:
            e.g.
                {"name":  "gpio master/slave test example",
                "child case num": 2,
                "config": "release",
                "env_tag": "UT_T2_1"}
     2. as list dict:
            e.g.
               [{"name":  "gpio master/slave test example1",
                "child case num": 2,
                "config": "release",
                "env_tag": "UT_T2_1"},
               {"name":  "gpio master/slave test example2",
                "child case num": 2,
                "config": "release",
                "env_tag": "UT_T2_1"}]

    """
    failed_cases = []
    case_config = format_test_case_config(extra_data)
    duts = {}
    for ut_config in case_config:
        Utility.console_log("Running unit test for config: " + ut_config, "O")
        for one_case in case_config[ut_config]:
            result = False
            junit_test_case = TinyFW.JunitReport.create_test_case("[{}] {}".format(ut_config, one_case["name"]))
            try:
                result = run_one_multiple_devices_case(duts, ut_config, env, one_case, junit_test_case)
            except Exception as e:
                junit_test_case.add_failure_info("Unexpected exception: " + str(e))
            finally:
                if result:
                    Utility.console_log("Success: " + one_case["name"], color="green")
                else:
                    failed_cases.append(one_case["name"])
                    Utility.console_log("Failed: " + one_case["name"], color="red")
                TinyFW.JunitReport.test_case_finish(junit_test_case)

    if failed_cases:
        Utility.console_log("Failed Cases:", color="red")
        for _case_name in failed_cases:
            Utility.console_log("\t" + _case_name, color="red")
        raise AssertionError("Unit Test Failed")


def run_one_multiple_stage_case(dut, one_case, failed_cases, junit_test_case):
    reset_dut(dut)

    dut.start_capture_raw_data()

    exception_reset_list = []

    for test_stage in range(one_case["child case num"]):
        # select multi stage test case name
        dut.write("\"{}\"".format(one_case["name"]))
        dut.expect("Running " + one_case["name"] + "...")
        # select test function for current stage
        dut.write(str(test_stage + 1))

        # we want to set this flag in callbacks (inner functions)
        # use list here so we can use append to set this flag
        stage_finish = list()

        def last_stage():
            return test_stage == one_case["child case num"] - 1

        def check_reset():
            if one_case["reset"]:
                assert exception_reset_list  # reboot but no exception/reset logged. should never happen
                result = False
                if len(one_case["reset"]) == len(exception_reset_list):
                    for i, exception in enumerate(exception_reset_list):
                        if one_case["reset"][i] not in exception:
                            break
                    else:
                        result = True
                if not result:
                    err_msg = "Reset Check Failed: \r\n\tExpected: {}\r\n\tGet: {}".format(one_case["reset"],
                                                                                           exception_reset_list)
                    Utility.console_log(err_msg, color="orange")
                    junit_test_case.add_error_info(err_msg)
            else:
                # we allow omit reset in multi stage cases
                result = True
            return result

        # expect callbacks
        def one_case_finish(result):
            """ one test finished, let expect loop break and log result """
            # handle test finish
            result = result and check_reset()
            output = dut.stop_capture_raw_data()
            if result:
                Utility.console_log("Success: " + one_case["name"], color="green")
            else:
                failed_cases.append(one_case["name"])
                Utility.console_log("Failed: " + one_case["name"], color="red")
                junit_test_case.add_failure_info(output)
            stage_finish.append("break")

        def handle_exception_reset(data):
            """
            just append data to exception list.
            exception list will be checked in ``handle_reset_finish``, once reset finished.
            """
            exception_reset_list.append(data[0])

        def handle_test_finish(data):
            """ test finished without reset """
            # in this scenario reset should not happen
            if int(data[1]):
                # case ignored
                Utility.console_log("Ignored: " + one_case["name"], color="orange")
                junit_test_case.add_skipped_info("ignored")
            # only passed in last stage will be regarded as real pass
            if last_stage():
                one_case_finish(not int(data[0]))
            else:
                Utility.console_log("test finished before enter last stage", color="orange")
                one_case_finish(False)

        def handle_next_stage(data):
            """ reboot finished. we goto next stage """
            if last_stage():
                # already last stage, should never goto next stage
                Utility.console_log("didn't finish at last stage", color="orange")
                one_case_finish(False)
            else:
                stage_finish.append("continue")

        while not stage_finish:
            try:
                dut.expect_any((RESET_PATTERN, handle_exception_reset),
                               (EXCEPTION_PATTERN, handle_exception_reset),
                               (ABORT_PATTERN, handle_exception_reset),
                               (FINISH_PATTERN, handle_test_finish),
                               (UT_APP_BOOT_UP_DONE, handle_next_stage),
                               timeout=one_case["timeout"])
            except ExpectTimeout:
                Utility.console_log("Timeout in expect", color="orange")
                one_case_finish(False)
                break
        if stage_finish[0] == "break":
            # test breaks on current stage
            break


@IDF.idf_unit_test(env_tag="UT_T1_1", junit_report_by_case=True)
def run_multiple_stage_cases(env, extra_data):
    """
    extra_data can be 2 types of value
    1. as dict: Mandantory keys: "name" and "child case num", optional keys: "reset" and others
    3. as list of string or dict:
               [case1, case2, case3, {"name": "restart from PRO CPU", "child case num": 2}, ...]

    :param extra_data: the case name or case list or case dictionary
    :return: None
    """

    case_config = format_test_case_config(extra_data)

    # we don't want stop on failed case (unless some special scenarios we can't handle)
    # this flag is used to log if any of the case failed during executing
    # Before exit test function this flag is used to log if the case fails
    failed_cases = []

    for ut_config in case_config:
        Utility.console_log("Running unit test for config: " + ut_config, "O")
        dut = env.get_dut("unit-test-app", app_path=ut_config, allow_dut_exception=True)
        dut.start_app()

        for one_case in case_config[ut_config]:
            junit_test_case = TinyFW.JunitReport.create_test_case("[{}] {}".format(ut_config, one_case["name"]))
            try:
                run_one_multiple_stage_case(dut, one_case, failed_cases, junit_test_case)
            except Exception as e:
                junit_test_case.add_failure_info("Unexpected exception: " + str(e))
                failed_cases.append(one_case["name"])
            finally:
                TinyFW.JunitReport.test_case_finish(junit_test_case)

    # raise exception if any case fails
    if failed_cases:
        Utility.console_log("Failed Cases:", color="red")
        for _case_name in failed_cases:
            Utility.console_log("\t" + _case_name, color="red")
        raise AssertionError("Unit Test Failed")


if __name__ == '__main__':
    run_multiple_devices_cases(extra_data={"name":  "gpio master/slave test example",
                                           "child case num": 2,
                                           "config": "release",
                                           "env_tag": "UT_T2_1"})
