# 🚗 ApolloSimFuzz (Drivora)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?logo=discord)](https://discord.gg/PpuwMwBWDS)

> **Note**
>
> The documentation is currently **incomplete**. At this stage, the repository primarily provides a **working pipeline** for testing **Baidu Apollo** using a **lightweight traffic simulator**.
>
> The framework has been **tested and shown to be stable** on the maintainer’s server setup.  
> Please feel free to **join our Discord** for quick discussions, and **open GitHub issues** for questions, bug reports, or suggestions.
>
> Contributions are very welcome — including documentation improvements, bug fixes, or functionality extensions.  
> Any feedback or support from the community is sincerely appreciated.

---

**ApolloSimFuzz** integrates **Baidu Apollo** with **TrafficSandbox**, a lightweight traffic simulation framework, to support **flexible, scalable, and closed-loop testing** of Apollo’s **decision-making functionalities** in lightweight simulation environments.

The framework is designed for **simulation-based testing and fuzzing**, where Apollo interacts with a traffic simulator through *perfect perception results* and *control commands*. This enables systematic evaluation of **decision-making** under diverse traffic scenarios without relying on full-stack, high-fidelity simulators.

---

## ✅ Pre-requisites

Before installation, please ensure the following dependencies are available on your system:

- [Anaconda](https://www.anaconda.com/)
- [Docker](https://www.docker.com/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

> ⚠️ **GPU support is required** for running Apollo modules.

---

## 📄 Documentation

- **Installation Guide**  
  👉 [Installation](documents/install.md)

---

## 📝 TODO

This project currently provides **basic testing functionality** (e.g., random testing) and is **under active development**.

Planned improvements include:

- [ ] Providing comprehensive documentation and usage examples  
- [ ] Refining minor components to improve robustness and stability  

---

## 📬 Contact

For questions, contributions, or collaboration inquiries:

- **Maintainer:** Mingfei Cheng  
- **Email:** [snowbirds.mf@gmail.com](mailto:snowbirds.mf@gmail.com)

---

## ❤️ Sponsorship

If you find this project useful for research or development, please consider supporting it via **GitHub Sponsors**.

---

## 📖 Citation

If you use **Drivora / ApolloSimFuzz** in your research, please cite the following papers:

```bibtex
@article{cheng2026drivora,
  title   = {Drivora: A Unified and Extensible Infrastructure for Search-based Autonomous Driving Testing},
  author  = {Cheng, Mingfei and Briand, Lionel and Zhou, Yuan},
  journal = {arXiv preprint arXiv:2601.05685},
  year    = {2026}
}

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

📌 More related references are listed in [reference.bib](reference.bib).

---

## 📄 License

This project is released under the **MIT License**.
See [LICENSE](LICENSE) for details.