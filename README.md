# cluster-impairment-operator



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
    bandwidth: 0 # kbit
    latency: 100 # ms
    loss: 0 # percent
    ingress: # uses ifb
      bandwidth: 0 # kbit
      latency: 10 # ms
      loss: 0 # percent
    egress:
      bandwidth: 0 #kbit
      latency: 0 # ms
      loss: 0 # percent
    link_flapping:
      enable: false
      down_time: 3
      up_time: 3
    node_selector:
      key: "node-role.kubernetes.io/worker"
      value: ""
```

## Limitations

### Multiple Impairments

You should avoid any impairment that applies to the same interface on the same node. There are potential conflicts.

Reason: First, if you apply ingress impairments to the same interface, the ifb interface will conflict. Second, the worker pod will attempt to remove all impairments before applying new ones.

Instead, take advantage of the full control of both ingress and egress impairments from within the same ClusterImpairment resource.

### Traffic Control (TC)

Traffic control is how cluster-impairment-operator applies the latency, bandwidth, and packet loss impairments. The limitation is Linux is not a realtime operating system, so the impairment will not be perfectly consistent.

### Link Flapping

When link flapping, if you flap the link that Kubernetes uses to communicate with the pods, you may be unable to remove the pod until the link is on long enough for Kubernetes to communicate with the impaired node.

In this case, it is helpful to set the duration properly instead of running for an indefinite or large amount of time, because the node will properly go back to the unimpaired state at that time.
