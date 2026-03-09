"""Tests for scaffold.py — metadata stub generation."""

import pytest
from pathlib import Path
from scripts.generators.flow_xml import generate_flow_xml
from scripts.generators.apex_stub import generate_apex_class, generate_apex_meta_xml
from scripts.generators.permission_set_xml import generate_permission_set_xml


class TestFlowXml:
    def test_basic_flow(self):
        xml = generate_flow_xml("Get_Order_Status")
        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml
        assert "<label>Get_Order_Status</label>" in xml
        assert "<status>Active</status>" in xml
        assert "<processType>AutoLaunchedFlow</processType>" in xml

    def test_flow_with_inputs(self):
        inputs = [{"name": "order_number", "type": "string", "description": "Order number"}]
        xml = generate_flow_xml("Get_Order_Status", inputs=inputs)
        assert "<name>order_number</name>" in xml
        assert "<isInput>true</isInput>" in xml
        assert "<dataType>String</dataType>" in xml

    def test_flow_with_outputs(self):
        outputs = [{"name": "status", "type": "string"}]
        xml = generate_flow_xml("Get_Order_Status", outputs=outputs)
        assert "<name>status</name>" in xml
        assert "<isOutput>true</isOutput>" in xml

    def test_bidirectional_variable(self):
        """Variables in both inputs and outputs should be merged."""
        inputs = [{"name": "order_id", "type": "string"}]
        outputs = [{"name": "order_id", "type": "string"}, {"name": "status", "type": "string"}]
        xml = generate_flow_xml("TestFlow", inputs=inputs, outputs=outputs)
        # order_id should appear once with isInput=true AND isOutput=true
        assert xml.count("<name>order_id</name>") == 1

    def test_boolean_type_mapping(self):
        outputs = [{"name": "is_active", "type": "boolean"}]
        xml = generate_flow_xml("TestFlow", outputs=outputs)
        assert "<dataType>Boolean</dataType>" in xml
        assert "<booleanValue>false</booleanValue>" in xml

    def test_placeholder_variable_when_no_outputs(self):
        xml = generate_flow_xml("TestFlow")
        assert "<name>placeholder_result</name>" in xml


class TestApexStub:
    def test_basic_class(self):
        code = generate_apex_class("GetOrderStatus")
        assert "public with sharing class GetOrderStatus" in code
        assert "@InvocableMethod" in code
        assert "public class Request" in code
        assert "public class Response" in code

    def test_class_with_inputs(self):
        inputs = [{"name": "order_number", "type": "string", "required": True}]
        code = generate_apex_class("GetOrderStatus", inputs=inputs)
        assert "public String order_number;" in code
        assert "@InvocableVariable" in code

    def test_class_with_outputs(self):
        outputs = [{"name": "status", "type": "string"}]
        code = generate_apex_class("GetOrderStatus", outputs=outputs)
        assert "public String status;" in code
        assert "res.status = 'TODO';" in code

    def test_number_type_mapping(self):
        outputs = [{"name": "count", "type": "number"}]
        code = generate_apex_class("TestClass", outputs=outputs)
        assert "public Decimal count;" in code

    def test_method_label(self):
        code = generate_apex_class("GetOrderStatus")
        assert "label='Get Order Status'" in code

    def test_meta_xml(self):
        xml = generate_apex_meta_xml()
        assert "<apiVersion>66.0</apiVersion>" in xml
        assert "<status>Active</status>" in xml


class TestPermissionSetXml:
    def test_basic(self):
        xml = generate_permission_set_xml("Test_Access", ["MyClass"])
        assert "<label>Test_Access</label>" in xml
        assert "<apexClass>MyClass</apexClass>" in xml
        assert "<enabled>true</enabled>" in xml

    def test_multiple_classes(self):
        xml = generate_permission_set_xml("Access", ["ClassA", "ClassB"])
        assert xml.count("<classAccesses>") == 2
        assert "<apexClass>ClassA</apexClass>" in xml
        assert "<apexClass>ClassB</apexClass>" in xml
