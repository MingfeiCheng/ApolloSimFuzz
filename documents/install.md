# Installation Guide for ApolloSimFuzz

This document provides step-by-step instructions for installing and setting up the environment for **ApolloSimFuzz**.

---

## ✅ Pre-requisites

Before installation, please ensure the following dependencies are available on your system:

- [Anaconda](https://www.anaconda.com/)
- [Docker](https://www.docker.com/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

> ⚠️ **GPU support is required** for running Baidu Apollo modules.

---

## 🛠️ Installation

### Step 1: Install Core Dependencies

We provide a unified `bash` script that automatically performs the following steps:

- Downloads Baidu Apollo
- Creates the corresponding Conda environment
- Builds the Docker image for **TrafficSandbox**

Run the installation script:

```bash
bash install.sh
````

If the installation is successful, you should see the following output:

```text
[ApolloSimFuzz] Installation completed successfully.
[ApolloSimFuzz] Can use conda environment: apollosimfuzz-7.0
```

After installation, the following artifacts should be available:

* A new directory:

  ```text
  apollo/
  ```

* A new Docker image (verify using `docker images`):

  ```text
  drivora/sandbox:latest
  ```

---

## 🧱 Build Baidu Apollo

Apollo must be compiled manually after the initial setup.

### Step 1: Navigate to the Apollo directory

```bash
cd apollo
```

### Step 2: Apply required patches

Apply the patches located in:

```text
apollo_bridge/patches/
```

Specifically:

* Move `apollo_bridge/patches/dev_start_ctn.sh` to:

  ```text
  apollo/scripts/
  ```

* Replace the following file to resolve build issues:

  ```text
  apollo/WORKSPACE
  ```

  with:

  ```text
  apollo_bridge/patches/WORKSPACE
  ```

### Step 3: Start the Apollo development container

```bash
bash docker/scripts/dev_start.sh
```

You should see a success message indicating that the container has started correctly.

### Step 4: Enter the container and build Apollo

```bash
bash docker/scripts/dev_into.sh
./apollo.sh build
```

> ⏱️ The build process may take a significant amount of time depending on your hardware configuration.

---

## 🚗 Build TrafficSandbox (Optional)

If the **TrafficSandbox Docker image was not successfully built** during the initial installation, you can build it manually as follows.

### Step 1: Enter the TrafficSandbox directory

```bash
cd TrafficSandbox
```

### Step 2: Build the TrafficSandbox Docker image

```bash
bash build.sh
```

After the build completes, verify the image:

```bash
docker images | grep drivora/sandbox
```

You should see the following output:

```text
drivora/sandbox   latest
```

### 🧪 Test Demo
Check and modify `config.yaml` and then execute:
```bash
python start_fuzzer.py
```