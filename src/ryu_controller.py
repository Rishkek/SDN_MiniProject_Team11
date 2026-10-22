"""
Standard Ryu OpenFlow 1.3 Controller Application.
Topic 27: Congestion Detection and Dynamic Traffic Rerouting.

Run in Linux/Mininet using:
    ryu-manager src/ryu_controller.py
"""

try:
    from ryu.base import app_manager
    from ryu.controller import ofp_event
    from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from ryu.ofproto import ofproto_v1_3
    from ryu.lib import hub
    RYU_AVAILABLE = True
except ImportError:
    RYU_AVAILABLE = False


if RYU_AVAILABLE:
    class RyuCongestionRerouter(app_manager.RyuApp):
        OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

        def __init__(self, *args, **kwargs):
            super(RyuCongestionRerouter, self).__init__(*args, **kwargs)
            self.datapaths = {}
            self.port_stats = {}  # (dpid, port_no): (prev_bytes, prev_time)
            self.threshold_bps = 8_000_000  # 8 Mbps congestion threshold
            self.active_path_port = 2  # Default: Port 2 (Path A)
            self.monitor_thread = hub.spawn(self._monitor)

        @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
        def switch_features_handler(self, ev):
            datapath = ev.msg.datapath
            self.datapaths[datapath.id] = datapath
            ofproto = datapath.ofproto
            parser = datapath.ofproto_parser

            # Install table-miss flow entry
            match = parser.OFPMatch()
            actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
            self.add_flow(datapath, 0, match, actions)
            self.logger.info(f"Switch s{datapath.id} registered with Ryu OpenFlow 1.3")

        def add_flow(self, datapath, priority, match, actions, buffer_id=None):
            ofproto = datapath.ofproto
            parser = datapath.ofproto_parser
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            mod = parser.OFPFlowMod(
                datapath=datapath,
                priority=priority,
                match=match,
                instructions=inst,
                buffer_id=buffer_id if buffer_id is not None else ofproto.OFP_NO_BUFFER
            )
            datapath.send_msg(mod)

        def _monitor(self):
            """Periodically queries port statistics from switches."""
            while True:
                for dp in self.datapaths.values():
                    self._request_port_stats(dp)
                hub.sleep(0.5)

        def _request_port_stats(self, datapath):
            parser = datapath.ofproto_parser
            req = parser.OFPPortStatsRequest(datapath, 0, datapath.ofproto.OFPP_ANY)
            datapath.send_msg(req)

        @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
        def port_stats_reply_handler(self, ev):
            body = ev.msg.body
            dpid = ev.msg.datapath.id

            if dpid == 1:  # Monitor ingress switch s1
                now = hub.time()
                for stat in body:
                    port_no = stat.port_no
                    if port_no in [2, 3]:  # Port 2 = Path A, Port 3 = Path B
                        key = (dpid, port_no)
                        if key in self.port_stats:
                            prev_bytes, prev_time = self.port_stats[key]
                            delta_time = now - prev_time
                            if delta_time > 0:
                                delta_bytes = stat.tx_bytes - prev_bytes
                                speed_bps = (delta_bytes * 8) / delta_time

                                # Check threshold on primary path
                                if port_no == 2 and speed_bps > self.threshold_bps and self.active_path_port == 2:
                                    self.logger.warning(
                                        f"[RYU ALERT] Congestion on Path-A! Rate: {speed_bps/1e6:.2f} Mbps > 8.0 Mbps. Rerouting to Path-B (Port 3)..."
                                    )
                                    self._reroute_to_path_b(ev.msg.datapath)
                                    self.active_path_port = 3

                        self.port_stats[key] = (stat.tx_bytes, now)

        def _reroute_to_path_b(self, datapath):
            parser = datapath.ofproto_parser
            # Match UDP packets to port 9999 and redirect to Port 3 (Path B)
            match = parser.OFPMatch(
                eth_type=0x0800,
                ip_proto=17,
                udp_dst=9999
            )
            actions = [parser.OFPActionOutput(3)]
            self.add_flow(datapath, priority=200, match=match, actions=actions)
            self.logger.info("[RYU SUCCESS] OpenFlow rule pushed: Flow H1->H2 dynamically rerouted via Path B.")

else:
    class RyuCongestionRerouter:
        """Stub class when Ryu is run in pure Python without ryu library."""
        def __init__(self, *args, **kwargs):
            print("Note: Ryu package is only required when running via 'ryu-manager'.")
