"""
This python module runs impairments on the specified interface, with the
specified impairments.

The interface and impairments are passed in using environment variables.

Variables:
- DURATION: Duration in seconds as int. Default: 60 (if no END_TIME set)
- START_TIME: The timestamp (epoch) when the impairment is supposed to start.
              Default: Current timestamp at time script is run.
- END_TIME: The timestamp (epoch) when the impairment will end. Overrides duration.
- INTERFACE: The interface to apply impairments. Default: ens1f1
- LATENCY: Latency in ms to apply. 0 to disable. Default 0.
- PACKET_LOSS: Percent packet loss (0-100). 0 to disable. Default 0.
- BANDWIDTH_LIMIT: The bandwidth limit in kbits. 0 to disable. Default 0.
- IMPAIRMENT_DIRECTION: ingress, egress, or both. Default egress.
                        Uses ifb for ingress impairments (a kernel module).
- LINK_FLAPPING: Whether to turn on and off the interface. (True/False) Default: False
- LINK_FLAP_DOWN_TIME: Time period to flap link down (Seconds)  Default: 2
- LINK_FLAP_UP_TIME: Time period to flap link down (Seconds). Default: 2
"""


import logging
import os
import subprocess
import time
import signal
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s : %(levelname)s : %(message)s')
logger = logging.getLogger('cluster-impairment')
logging.Formatter.converter = time.gmtime

running = True

def on_shutdown(self, *args):
  global running
  running = False

def command(cmd, dry_run, cmd_directory="", mask_output=False, mask_arg=0, no_log=False, fail_on_error=False):
  if cmd_directory != "":
    logger.debug("Command Directory: {}".format(cmd_directory))
    working_directory = os.getcwd()
    os.chdir(cmd_directory)
  if dry_run:
    cmd.insert(0, "echo")
  if mask_arg == 0:
    logger.info("Command: {}".format(" ".join(cmd)))
  else:
    logger.info("Command: {} {} {}".format(" ".join(cmd[:mask_arg - 1]), "**(Masked)**", " ".join(cmd[mask_arg:])))
  process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

  output = ""
  while True:
    output_line = process.stdout.readline()
    if output_line.strip() != "":
      if not no_log:
        if not mask_output:
          logger.info("Output : {}".format(output_line.strip()))
        else:
          logger.info("Output : **(Masked)**")
      if output == "":
        output = output_line.strip()
      else:
        output = "{}\n{}".format(output, output_line.strip())
    return_code = process.poll()
    if return_code is not None:
      for output_line in process.stdout.readlines():
        if output_line.strip() != "":
          if not no_log:
            if not mask_output:
              logger.info("Output : {}".format(output_line.strip()))
            else:
              logger.info("Output : **(Masked)**")
          if output == "":
            output = output_line
          else:
            output = "{}\n{}".format(output, output_line.strip())
      logger.debug("Return Code: {}".format(return_code))
      break
  if cmd_directory != "":
    os.chdir(working_directory)
  if fail_on_error and return_code != 0:
    logger.error("Error issuing command \"{}\".".format(cmd_directory))
    logger.error(output)
    sys.exit(1)
  return return_code, output

def parse_tc_netem_args():
  """
  Uses the environment variables to construct an array of params for netem

  Currently supports latency, packet loss, and bandwidth limit as documented
  in the module docstring.
  """
  args = {}

  latency_evar = int(os.environ.get("LATENCY", 0))
  packet_loss_evar = float(os.environ.get("PACKET_LOSS", 0))
  bandwidth_limit_evar = int(os.environ.get("BANDWIDTH_LIMIT", 0))
  logger.info(bandwidth_limit_evar)
  if latency_evar > 0:
    args["latency"] = ["delay", "{}ms".format(latency_evar)]
  if packet_loss_evar > 0:
    args["packet loss"] = ["loss", "{}%".format(packet_loss_evar)]
  if bandwidth_limit_evar > 0:
    args["bandwidth limit"] = ["rate", "{}kbit".format(bandwidth_limit_evar)]

  return args


def apply_tc_netem(interfaces, impairments, dry_run=False):
  if len(impairments) > 1:
    logger.info("Applying {} impairments".format(", ".join(impairments.keys())))
  elif len(impairments) == 1:
    logger.info("Applying only {} impairment".format(list(impairments.keys())[0]))
  else:
    logger.warn("Invalid state. Applying no impairments.")

  for interface in interfaces:
    tc_command = ["tc", "qdisc", "add", "dev", interface, "root", "netem"]
    for impairment in impairments.values():
      tc_command.extend(impairment)
    rc, _ = command(tc_command, dry_run)
    if rc != 0:
      logger.error("Applying latency and packet loss failed, tc rc: {}. Did you forget to run as privileged with host-network?".format(rc))
      _, output = command(["ifconfig"], False)
      print(output)
      sys.exit(1)


def remove_tc_netem(interfaces, dry_run=False, ignore_errors=False):
  logger.info("Removing bandwidth, latency, and packet loss impairments")
  for interface in interfaces:
    tc_command = ["tc", "qdisc", "del", "dev", interface, "root", "netem"]
    rc, _ = command(tc_command, dry_run)
    if rc != 0 and not ignore_errors:
      logger.error("Removing latency and packet loss failed, tc rc: {}".format(rc))
      sys.exit(1)

def setup_ifb(interface, dry_run):
  logger.info("Setting up ifb interface")
  command(["modprobe", "ifb"], dry_run, fail_on_error=True)
  command(["ip", "link", "set", "dev", "ifb0", "up"], dry_run, fail_on_error=True)
  command(["tc", "qdisc", "add", "dev", interface, "ingress"], dry_run, fail_on_error=True)
  command(["tc", "filter", "add", "dev", interface, "parent", "ffff:",
            "protocol", "ip", "u32", "match", "u32", "0", "0", "flowid",
            "1:1", "action", "mirred", "egress", "redirect", "dev", "ifb0"],
            dry_run, fail_on_error=True)

def remove_ifb(interface, dry_run):
  logger.info("Removing IFB")
  command(["tc", "qdisc", "del", "dev", interface, "ingress"], dry_run)
  command(["ip", "link", "set", "dev", "ifb0", "down"], dry_run)
  command(["modprobe", "-r", "ifb"], dry_run)

def set_flap_links(interface, up, dry_run, ignore_errors=False):
  logger.info("Flapping links " + up)
  ip_command = ["ip", "link", "set", interface, up]
  rc, _ = command(ip_command, dry_run)
  if rc != 0 and not ignore_errors:
    logger.error("RWN workload, ip link set {} {} rc: {}".format(interface, up, rc))
    sys.exit(1)

def main():

  logger.info("Impairment script running")

  # It is important that this script knows when the pod is
  # being shut down so that the impairments can be removed.
  global running
  signal.signal(signal.SIGINT, on_shutdown)
  signal.signal(signal.SIGTERM, on_shutdown)

  # Now, the impairments

  start_time = time.time()
  netem_impairments = parse_tc_netem_args()
  duration = int(os.environ.get("DURATION", -1)) # Seconds
  start_time = int(os.environ.get("START_TIME", time.time())) # Epoch
  end_time = int(os.environ.get("END_TIME", -1)) # Epoch
  inbound_interface = os.environ.get("INTERFACE", "ens1f1")
  dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
  flap_links = os.environ.get("LINK_FLAPPING", "false").lower() == "true"
  link_flap_down = int(os.environ.get("LINK_FLAP_DOWN_TIME", 1))
  link_flap_up = int(os.environ.get("LINK_FLAP_UP_TIME", 1))
  impairment_direction = os.environ.get("IMPAIRMENT_DIRECTION", "egress").lower()

  if end_time == -1:
    if duration == -1:
      duration = 60
    end_time = start_time + duration

  if len(netem_impairments) or flap_links:
    logger.info("Running impairments")
  else:
    logger.warn("No impairments. Exiting")
    return

  current_time = time.time()

  if current_time < start_time and running:
    logger.info("Waiting to run impairments")
  while current_time < start_time and running:
    time.sleep(.1)
    current_time = time.time()

  if len(netem_impairments):
    interfaces = []
    if impairment_direction != "ingress":
      interfaces.append(inbound_interface)
    if impairment_direction != "egress":
      interfaces.append("ifb0")

    # Remove, just in case.
    remove_tc_netem(
      interfaces,
      dry_run,
      True)
    remove_ifb(inbound_interface, dry_run)

    if impairment_direction != "egress":
      setup_ifb(inbound_interface, dry_run)

    apply_tc_netem(
        interfaces,
        netem_impairments,
        dry_run)
  else:
    logger.info("No netem impairments")

  if flap_links:
    link_flap_count = 1
    set_flap_links(inbound_interface, "down", dry_run)
    next_flap_time = time.time() + link_flap_down
    links_down = True

  wait_logger = 0
  while current_time < end_time and running:
    if flap_links:
      if current_time >= next_flap_time:
        if links_down:
          links_down = False
          set_flap_links(inbound_interface, "up", dry_run)
          next_flap_time = time.time() + link_flap_up
        else:
          links_down = True
          link_flap_count += 1
          set_flap_links(inbound_interface, "down", dry_run)
          next_flap_time = time.time() + link_flap_down

    time.sleep(.1)
    wait_logger += 1
    if wait_logger >= 100:
      logger.info("Remaining impairment duration: {}".format(round(end_time - current_time, 1)))
      wait_logger = 0
    current_time = time.time()

  if not running:
    logger.warn("Ending early due to pod/system termination")

  if flap_links:
    set_flap_links(inbound_interface, "up", dry_run, True)

  if len(netem_impairments):
    # Done
    remove_tc_netem(
      interfaces,
      dry_run)

    if impairment_direction != "egress":
      remove_ifb(inbound_interface, dry_run)

  # Sleep until ended
  while running:
    time.sleep(0.1)

if __name__ == '__main__':
  sys.exit(main())
