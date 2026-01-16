
```
ApolloAgent
├── run()
├── stop()
├── _receive_control()
├── _publish_sensor()
├── _request_snapshot()
│   ├── _build_route_message()
│   ├── _build_chassis_message()
│   ├── _build_localization_message()
│   ├── _build_perfect_obstacle_message()
│   └── _build_traffic_light_message()
├── RecorderMixin
│   ├── start_record()
│   ├── stop_record()
├── LoggingMixin
│   ├── get_instance_logger()
│   ├── exception-safe logger calls
└── SandboxMessengerAdapter
    └── ApolloMessenger 控制封装

```