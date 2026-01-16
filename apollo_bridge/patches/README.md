## 🩹 Usage of Patches

To ensure smooth integration of Apollo with **Drivora-ApolloSim** and the **TrafficSandbox**, several patches must be applied.

---

### 1. WORKSPACE

In Apollo 7.0, the build process may encounter known [issues](https://github.com/ApolloAuto/apollo/issues/14374).  
To resolve this, please replace the default `WORKSPACE` file:

```bash
# From Drivora/ApolloSim/apollo_bridge/patches
COPY patches/WORKSPACE to apollo/WORKSPACE
```

---

### 2. Container Start Script

To support **multiple instances** and simplify container startup, use the patched start script:

```bash
COPY patches/dev_start_ctn.sh to apollo/docker/scripts/
```

This custom script is used in **Drivora** to start Apollo containers consistently.

---

### 3. Controller Parameters

Controller parameters have been tuned to better suit **TrafficSandbox**.  
Please replace the configuration file as follows:

```bash
COPY patches/control_conf.pb.txt to apollo/modules/control/conf/
```

---

✅ After applying these patches, Apollo should build and run smoothly within the Drivora-ApolloSim environment.
