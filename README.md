# cluster-impairment-operator

cluster-impairment-operator is an operator designed to automate the application of impairments to the nodes in a cluster.

## Features

Traffic Direction:
* Egress impairments affect the traffic going out.
* Ingress impairments affect the traffic coming in.
  *  Ingress impairments require the kernel module IFB.

### Impairments

| Impairment    | Description                             | Unit    | Uses Netem |
|---------------|-----------------------------------------|---------|------------|
| Bandwidth     | The bandwidth limit                     | kbit/s  | Yes        |
| Latency       | The delay of the packets                | ms      | Yes        |
| Packet Loss   | The percent of packets that are dropped | percent | Yes        |
| Link Flapping | Turns the interface on and off          | bool    | No         |

On the tested environment (RHEL CoreOS 48.84), the impairments can be used alongside link flapping.


## Configuration

Here is an example of the ClusterImpairment custom resource.
```yaml
apiVersion: apps.redhat.com/v1alpha1
kind: ClusterImpairment
metadata:
  name: test-impairment-cr
spec:
  impairments:
    duration: 30 # seconds
    start_delay: 5 # seconds. It typically takes about 2-3 seconds for the Daemonset to run
    interfaces:
    - "ens2f0"
    ingress: # uses ifb
      bandwidth: 0 # kbit
      latency: 10 # ms
      loss: 0 # percent
    egress:
      bandwidth: 0 # kbit
      latency: 100 # ms
      loss: 0 # percent
    link_flapping:
      enable: false
      down_time: 3 # Seconds
      up_time: 3 # Seconds
    node_selector:
      key: "node-role.kubernetes.io/worker"
      value: ""
```

#### Interfaces

The interfaces configuration option is a list of all interfaces that the impairments should be applied to. The current implementation will error out once it hits an invalid interface.

If an invalid interface is found, it will print out the list of interfaces.

#### Node Selector

There is a limit and minimum of one node selector. The default node selector is all worker nodes, but you can change it to whatever node selector you want by setting the key and value.

Note: The daemonset is not setup to work on master nodes, so even if the node selector matches master nodes, it will not apply to them.

#### Duration

The duration the script runs in seconds. It will try to sync the start and end time between all pods.
If set to -1, it will run indefinitely (a year), until you remove the ClusterImpairment custom resource. This is good for testing that requires steady impairments.

If the script is link flapping, set this to be short enough so that if the link flap interrupts communication between the nodes, the daemonset will remove itself.

#### Start Delay

The delay before starting the script. If you want the pods to be in sync, a minimum of a few seconds should be used because the pods take time to start up.

You can also utilize this feature to run an impairment after another. Just apply two resources at the same time, but add the duration and start delay of the first to the start delay of the second.

#### Ingress and Egress

The configuration sections "ingress" and "egress" apply to each direction. They override the bidirectional values that are outside of these sections.

##### Examples:

**Example 1**
In this example, latency is set to 100ms, but the ingress latency is set to 10ms. So the latency to the interface will end up being 10ms, but 100ms going out. When pinging, this will result in 110ms of latency.
```yaml
apiVersion: apps.redhat.com/v1alpha1
kind: ClusterImpairment
metadata:
  name: uneven-latency
spec:
  impairments:
    duration: 60
    start_delay: 5
    interfaces:
    - "ens2f0"
    ingress:
      latency: 10 # ms
    egress:
      latency: 100 # ms
```

**Example 2**
In this example, link flapping will be enabled, and it will turn the interface on and off every 2 minutes. That is long enough for kubernetes to determine that a node is unavailable.

```yaml
apiVersion: apps.redhat.com/v1alpha1
kind: ClusterImpairment
metadata:
  name: two-min-flap
spec:
  impairments:
    duration: 480
    start_delay: 5
    interfaces:
    - "ens2f0"
    link_flapping:
      enable: true
      down_time: 120 # Seconds
      up_time: 120 # Seconds
```

**Example 3**
In this example, a realistic set of impairments is applied to ens2f0 and for 30 seconds:

```yaml
apiVersion: apps.redhat.com/v1alpha1
kind: ClusterImpairment
metadata:
  name: typical-scenario
spec:
  impairments:
    duration: 30 # seconds
    start_delay: 5 # seconds
    interfaces:
    - "ens2f0"
    - "eno1"
    egress:
      latency: 50 # ms. Bidirectional, so total of 100ms
    ingress:
      latency: 50 # ms. Bidirectional, so total of 100ms
    loss: 0.02 # percent
```

**Example 4**
In this example, a combination of latency, packet loss, bandwidth, and link flapping is applied.
```yaml
apiVersion: apps.redhat.com/v1alpha1
kind: ClusterImpairment
metadata:
  name: all-impairments
spec:
  impairments:
    duration: 480 # seconds
    start_delay: 5 # seconds
    interfaces:
    - "ens2f0"
    egress:
      latency: 50 # ms. Bidirectional, so total of 100ms
      loss: 0.02 # percent
      bandwidth: 1000 # 1000 kbit/s, about 1 mbit/s
    ingress:
      latency: 50 # ms. Bidirectional, so total of 100ms
      loss: 0.02 # percent
      bandwidth: 1000 # 1000 kbit/s, about 1 mbit/s
    link_flapping:
      enable: true
      down_time: 30 # Seconds
      up_time: 120 # Seconds
```

## Setup

### Requirements

1. You need make installed
2. You need access to the kubernetes cluster with a kubeconfig.

### Installation

To run using the current latest image:
1. Clone the repository
2. Run `make deploy` with the kubeconfig in the environment variables.

To run with your own code, there are more steps.

1. Fork the repository
2. Clone to a machine that has access to the Kubernetes cluster and the kubeconfig.
3. Modify the makefile to change the `IMG` variable to your image repository. If you do not have podman installed, also change podman to docker.
4. Run `make docker-build` then `make docker-push`.
5. Then run `make deploy`

### Deploying from operator-hub

Not setup. Planned for later.

## Running impairments

First, configure a ClusterImpairment type's spec with the information for the impairment you want to run. Most importantly, set the interface(s). You can list the interfaces with `ifconfig`. If an invalid interface is set, the pod's logs will show `ifconfig` output.

Once the clusterimpairment type is set, apply it and it will work.

## Limitations

### Multiple Impairments

You should avoid any impairment that applies to the same interface on the same node. There are potential conflicts.

Reason: First, if you apply ingress impairments to the same interface, the ifb interface will conflict. Second, the worker pod will attempt to remove 
all impairments before applying new ones.

Instead, take advantage of the full control of both ingress and egress impairments from within the same ClusterImpairment resource.

### Traffic Control (TC)

Traffic control is how cluster-impairment-operator applies the latency, bandwidth, and packet loss impairments. The limitation is Linux is not a realtime operating system, so the impairment will not be perfectly consistent.

### Link Flapping

When link flapping, if you flap the link that Kubernetes uses to communicate with the pods, you may be unable to remove the pod until the link is on long enough for Kubernetes to communicate with the impaired node.

In this case, it is helpful to set the duration properly instead of running for an indefinite or large amount of time, because the node will properly go back to the unimpaired state at that time.

If the cluster becomes offline due to the link flapping when you do not want it to be offline, soft restarting the nodes after removing the custom resource should remove all impairments.
