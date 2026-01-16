# 🚗 ApolloSimFuzz

**ApolloSimFuzz** integrates **Baidu Apollo** with **TrafficSandbox**, a lightweight traffic simulation framework, to support **flexible, scalable, and closed-loop testing** of Baidu Apollo’s **decision-making functionalities** in lightweight simulation environments.

The framework is designed for **simulation-based testing and fuzzing**, where Apollo interacts with a traffic simulator through sensor inputs and control commands, enabling systematic evaluation of decision-making robustness under diverse traffic scenarios.

---

## ✅ Pre-requisites

Before installation, please ensure the following dependencies are available on your system:

- [Anaconda](https://www.anaconda.com/)
- [Docker](https://www.docker.com/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

> ⚠️ GPU support is required for running Apollo modules.

---

## 🛠️ Installation

### Step 1: Navigate to the ApolloSim directory

```bash
cd Drivora/ApolloSim
````

### Step 2: Run the installation script

```bash
bash install.sh
```

This script will automatically:

* Clone the official [Baidu Apollo repository](https://github.com/ApolloAuto/apollo) into
  `Drivora/ApolloSim/apollo`
* Create a Conda environment named
  `drivora-apollo-${APOLLO_VERSION}`
* Install all required Python dependencies listed in `requirements.txt`
* Build the **TrafficSandbox** Docker image from
  `Drivora/ApolloSim/TrafficSandbox`

> 📌 The Apollo version currently used is specified in the `VERSION` file.

---

## ⚙️ Build Baidu Apollo

Due to Apollo’s build and runtime requirements, several manual steps are required.

---

### 🔧 Step 1: Apply Apollo Patches

Navigate to the Apollo directory:

```bash
cd Drivora/ApolloSim/apollo
```

Apply the patches located in:

```text
Drivora/ApolloSim/apollo_bridge/patches/
```

Please follow the detailed instructions provided in:

```text
apollo_bridge/patches/README.md
```

These patches adapt Apollo for integration with **TrafficSandbox** and the ApolloSimFuzz workflow.

---

### 🏗️ Step 2: Build Apollo inside Docker

#### 1. Start Apollo’s development Docker container

```bash
bash docker/scripts/dev_start.sh
```

You should see a success message indicating that the container has started correctly.

#### 2. Enter the container

```bash
bash docker/scripts/dev_into.sh
```

#### 3. Build Apollo

Inside the container, run:

```bash
./apollo.sh build
```

> ⏱️ The build process may take a significant amount of time depending on your hardware.

---

## 🚦 Build TrafficSandbox

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

You should see the following image:

```text
drivora/sandbox   latest
```

### Step 3: Test
Check and modify `config.yaml` and then execute:
```bash
python start_fuzzer.py
```

---

## 📝 TODO

This project currently provides **basic testing functionality** (e.g., random testing) and is **under active development**.
The framework is usable, and feedback or issue reports are highly welcome.

* [ ] Provide comprehensive documentation and usage examples
* [ ] Refine minor components to improve robustness and stability

---

## 📬 Contact

For questions, contributions, or collaboration inquiries:

* **Maintainer:** Mingfei Cheng
* **Email:** [snowbirds.mf@gmail.com](mailto:snowbirds.mf@gmail.com)
* **Affiliation:**
  School of Computing and Information Systems
  Singapore Management University

---

## 📖 Citation

If you use **Drivora / ApolloSimFuzz** in your research, please cite the following papers:

```bibtex
@inproceedings{cheng2025decictor,
  title     = {Decictor: Towards Evaluating the Robustness of Decision-Making in Autonomous Driving Systems},
  author    = {Cheng, Mingfei and Xie, Xiaofei and Zhou, Yuan and Wang, Junjie and Meng, Guozhu and Yang, Kairui},
  booktitle = {Proceedings of the 47th IEEE/ACM International Conference on Software Engineering (ICSE)},
  pages     = {1--13},
  year      = {2025},
  organization = {IEEE}
}

@inproceedings{cheng2023behavexplor,
  title     = {Behavexplor: Behavior Diversity Guided Testing for Autonomous Driving Systems},
  author    = {Cheng, Mingfei and Zhou, Yuan and Xie, Xiaofei},
  booktitle = {Proceedings of the 32nd ACM SIGSOFT International Symposium on Software Testing and Analysis (ISSTA)},
  pages     = {488--500},
  year      = {2023}
}
```

📌 A consolidated `.bib` file will be provided in future releases.

---

## 📄 License

This project is released under the **MIT License**.
See [LICENSE](../LICENSE) for details.