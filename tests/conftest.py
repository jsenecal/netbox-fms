from dcim.models import FrontPort, RearPort

# Counter to ensure unique RearPort names across tests
_rp_counter = 0


def make_front_port(device, name, module=None, port_type="lc"):
    """
    Create a FrontPort with its required backing RearPort.
    NetBox FrontPort requires rear_port + rear_port_position.
    """
    global _rp_counter
    _rp_counter += 1
    rp = RearPort.objects.create(
        device=device,
        name=f"_RP-{_rp_counter}",
        type=port_type,
        positions=1,
    )
    kwargs = {
        "device": device,
        "name": name,
        "type": port_type,
        "rear_port": rp,
        "rear_port_position": 1,
    }
    if module is not None:
        kwargs["module"] = module
    return FrontPort.objects.create(**kwargs)
