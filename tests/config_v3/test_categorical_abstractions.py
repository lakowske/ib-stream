#!/usr/bin/env python3
"""
Unit tests for categorical abstractions in Configuration System v3.

Tests the mathematical properties and laws of Result monad, Monoids, 
and Categorical constraints to ensure correctness of Category Theory structures.
"""

import pytest
import sys
from pathlib import Path

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import categorical abstractions directly to avoid ibapi dependency
import importlib.util

def load_module(module_name: str, file_path: str):
    """Load module directly from file path"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Load categorical module
categorical_path = project_root / "ib-util" / "ib_util" / "categorical.py"
categorical = load_module("categorical", str(categorical_path))

# Import types and classes
Result = categorical.Result
Success = categorical.Success
Error = categorical.Error
pure = categorical.pure
sequence_results = categorical.sequence_results
DictMonoid = categorical.DictMonoid
BoundedConstraint = categorical.BoundedConstraint
RangeConstraint = categorical.RangeConstraint
validate_log_level = categorical.validate_log_level


class TestResultMonad:
    """Test Result monad laws and operations"""
    
    def test_monad_left_identity(self):
        """Test left identity law: pure(a).bind(f) = f(a)"""
        def f(x):
            return Success(x * 2) if x > 0 else Error("negative")
        
        a = 5
        left = pure(a).bind(f)
        right = f(a)
        
        assert left.is_success() == right.is_success()
        if left.is_success():
            assert left.unwrap() == right.unwrap()
        else:
            assert left.error() == right.error()
    
    def test_monad_right_identity(self):
        """Test right identity law: m.bind(pure) = m"""
        m1 = Success(42)
        m2 = Error("test error")
        
        # Success case
        result1 = m1.bind(pure)
        assert result1.is_success()
        assert result1.unwrap() == m1.unwrap()
        
        # Error case
        result2 = m2.bind(pure)
        assert result2.is_error()
        assert result2.error() == m2.error()
    
    def test_monad_associativity(self):
        """Test associativity law: m.bind(f).bind(g) = m.bind(lambda x: f(x).bind(g))"""
        def f(x):
            return Success(x + 10)
        
        def g(x):
            return Success(x * 2)
        
        m = Success(5)
        
        # Left side: m.bind(f).bind(g)
        left = m.bind(f).bind(g)
        
        # Right side: m.bind(lambda x: f(x).bind(g))
        right = m.bind(lambda x: f(x).bind(g))
        
        assert left.is_success() == right.is_success()
        assert left.unwrap() == right.unwrap()
        assert left.unwrap() == 30  # (5 + 10) * 2
    
    def test_functor_identity(self):
        """Test functor identity law: fmap(id, x) = x"""
        identity = lambda x: x
        
        success = Success(42)
        error = Error("test")
        
        assert success.map(identity).unwrap() == success.unwrap()
        assert error.map(identity).error() == error.error()
    
    def test_functor_composition(self):
        """Test functor composition law: fmap(f ∘ g, x) = fmap(f, fmap(g, x))"""
        f = lambda x: x * 2
        g = lambda x: x + 10
        
        m = Success(5)
        
        # Left side: fmap(f ∘ g, x)
        left = m.map(lambda x: f(g(x)))
        
        # Right side: fmap(f, fmap(g, x))
        right = m.map(g).map(f)
        
        assert left.unwrap() == right.unwrap()
        assert left.unwrap() == 30  # (5 + 10) * 2
    
    def test_success_operations(self):
        """Test Success case operations"""
        success = Success(42)
        
        assert success.is_success()
        assert not success.is_error()
        assert success.unwrap() == 42
        
        # Test bind
        doubled = success.bind(lambda x: Success(x * 2))
        assert doubled.is_success()
        assert doubled.unwrap() == 84
        
        # Test map
        mapped = success.map(lambda x: x + 10)
        assert mapped.is_success()
        assert mapped.unwrap() == 52
    
    def test_error_operations(self):
        """Test Error case operations"""
        error = Error("test error")
        
        assert not error.is_success()
        assert error.is_error()
        assert error.error() == "test error"
        
        # Test bind - should propagate error
        result = error.bind(lambda x: Success(x * 2))
        assert result.is_error()
        assert result.error() == "test error"
        
        # Test map - should propagate error
        mapped = error.map(lambda x: x + 10)
        assert mapped.is_error()
        assert mapped.error() == "test error"
    
    def test_error_access_safety(self):
        """Test that accessing wrong case raises appropriate errors"""
        success = Success(42)
        error = Error("test")
        
        with pytest.raises(ValueError, match="Success result has no error"):
            success.error()
            
        with pytest.raises(ValueError, match="Error result cannot be unwrapped"):
            error.unwrap()
    
    def test_sequence_results(self):
        """Test sequence_results function"""
        # All success
        results = [Success(1), Success(2), Success(3)]
        sequenced = sequence_results(results)
        assert sequenced.is_success()
        assert sequenced.unwrap() == [1, 2, 3]
        
        # Contains error
        results_with_error = [Success(1), Error("failed"), Success(3)]
        sequenced_error = sequence_results(results_with_error)
        assert sequenced_error.is_error()
        assert sequenced_error.error() == "failed"
        
        # Empty list
        empty = sequence_results([])
        assert empty.is_success()
        assert empty.unwrap() == []


class TestDictMonoid:
    """Test dictionary monoid laws and operations"""
    
    def test_monoid_identity_left(self):
        """Test left identity law: empty ⊕ a = a"""
        monoid = DictMonoid()
        a = {"key": "value", "nested": {"inner": 42}}
        
        result = monoid.combine(monoid.empty(), a)
        assert result == a
    
    def test_monoid_identity_right(self):
        """Test right identity law: a ⊕ empty = a"""
        monoid = DictMonoid()
        a = {"key": "value", "nested": {"inner": 42}}
        
        result = monoid.combine(a, monoid.empty())
        assert result == a
    
    def test_monoid_associativity(self):
        """Test associativity law: (a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)"""
        monoid = DictMonoid()
        
        a = {"x": 1, "nested": {"a": "A"}}
        b = {"y": 2, "nested": {"b": "B"}}  
        c = {"z": 3, "nested": {"c": "C"}}
        
        # Left side: (a ⊕ b) ⊕ c
        left = monoid.combine(monoid.combine(a, b), c)
        
        # Right side: a ⊕ (b ⊕ c)
        right = monoid.combine(a, monoid.combine(b, c))
        
        assert left == right
        expected = {
            "x": 1, "y": 2, "z": 3,
            "nested": {"a": "A", "b": "B", "c": "C"}
        }
        assert left == expected
    
    def test_deep_merge(self):
        """Test deep dictionary merging"""
        monoid = DictMonoid()
        
        base = {
            "server": {"host": "localhost", "port": 8080},
            "features": {"logging": True},
            "list": [1, 2]
        }
        
        override = {
            "server": {"port": 9000, "timeout": 30},
            "features": {"caching": True},
            "new_key": "new_value",
            "list": [3, 4]  # Lists are replaced, not merged
        }
        
        result = monoid.combine(base, override)
        
        expected = {
            "server": {"host": "localhost", "port": 9000, "timeout": 30},
            "features": {"logging": True, "caching": True},
            "new_key": "new_value",
            "list": [3, 4]
        }
        
        assert result == expected
    
    def test_fold_operation(self):
        """Test fold operation with multiple dictionaries"""
        monoid = DictMonoid()
        
        dicts = [
            {"a": 1},
            {"b": 2},
            {"a": 10, "c": 3},  # 'a' gets overridden
            {"d": 4}
        ]
        
        result = monoid.fold(dicts)
        expected = {"a": 10, "b": 2, "c": 3, "d": 4}
        
        assert result == expected
    
    def test_empty_fold(self):
        """Test fold with empty list returns identity"""
        monoid = DictMonoid()
        result = monoid.fold([])
        assert result == monoid.empty()


class TestCategoricalConstraints:
    """Test categorical constraints and validation"""
    
    def test_range_constraint_valid(self):
        """Test range constraint with valid values"""
        port_constraint = RangeConstraint(1024, 65535, inclusive=True)
        
        # Valid ports
        assert port_constraint.check(1024).is_success()
        assert port_constraint.check(8080).is_success()
        assert port_constraint.check(65535).is_success()
        
        # Check returned values
        assert port_constraint.check(8080).unwrap() == 8080
    
    def test_range_constraint_invalid(self):
        """Test range constraint with invalid values"""
        port_constraint = RangeConstraint(1024, 65535, inclusive=True)
        
        # Invalid ports
        result_low = port_constraint.check(80)
        assert result_low.is_error()
        assert "not in range 1024 ≤ x ≤ 65535" in result_low.error()
        
        result_high = port_constraint.check(70000)
        assert result_high.is_error()
        assert "not in range 1024 ≤ x ≤ 65535" in result_high.error()
    
    def test_range_constraint_exclusive(self):
        """Test range constraint with exclusive bounds"""
        constraint = RangeConstraint(0, 10, inclusive=False)
        
        # Exclusive bounds
        assert constraint.check(0).is_error()
        assert constraint.check(10).is_error()
        
        # Valid values
        assert constraint.check(5).is_success()
        assert constraint.check(0.1).is_success()
        assert constraint.check(9.9).is_success()
    
    def test_bounded_constraint(self):
        """Test bounded constraint with enum-like values"""
        from enum import Enum
        
        class Color(Enum):
            RED = "red"
            GREEN = "green" 
            BLUE = "blue"
        
        color_constraint = BoundedConstraint(list(Color), "colors")
        
        # Valid colors
        assert color_constraint.check(Color.RED).is_success()
        assert color_constraint.check(Color.BLUE).is_success()
        
        # Invalid color (not in enum)
        class BadColor(Enum):
            YELLOW = "yellow"
            
        result = color_constraint.check(BadColor.YELLOW)
        assert result.is_error()
        assert "Invalid colors" in result.error()
    
    def test_log_level_validation(self):
        """Test log level validation with categorical constraints"""
        # Valid log levels
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        
        for level in valid_levels:
            result = validate_log_level(level)
            assert result.is_success()
            assert result.unwrap() == level
            
        # Case insensitive
        result_lower = validate_log_level("debug")
        assert result_lower.is_success()
        assert result_lower.unwrap() == "DEBUG"
        
        # Invalid log level
        result_invalid = validate_log_level("TRACE")
        assert result_invalid.is_error()
        assert "Invalid log level: TRACE" in result_invalid.error()
        assert "Must be one of ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']" in result_invalid.error()
    
    def test_constraint_composition_and(self):
        """Test constraint composition with AND logic"""
        positive_constraint = RangeConstraint(0, float('inf'), inclusive=False)
        small_constraint = RangeConstraint(float('-inf'), 100, inclusive=True)
        
        # Compose with AND
        combined = positive_constraint.and_then(small_constraint)
        
        # Valid: positive and small
        assert combined.check(50).is_success()
        
        # Invalid: negative (fails first constraint)
        assert combined.check(-10).is_error()
        
        # Invalid: too large (fails second constraint)
        assert combined.check(200).is_error()
    
    def test_constraint_composition_or(self):
        """Test constraint composition with OR logic"""
        small_constraint = RangeConstraint(0, 10, inclusive=True)
        large_constraint = RangeConstraint(90, 100, inclusive=True)
        
        # Compose with OR
        combined = small_constraint.or_else(large_constraint)
        
        # Valid: satisfies first constraint
        assert combined.check(5).is_success()
        
        # Valid: satisfies second constraint
        assert combined.check(95).is_success()
        
        # Invalid: satisfies neither constraint
        result = combined.check(50)
        assert result.is_error()
        assert "Both constraints failed" in result.error()


class TestCategoricalProperties:
    """Property-based tests for categorical laws"""
    
    def test_result_monad_properties(self):
        """Test Result monad satisfies required properties across multiple values"""
        test_values = [0, 1, -1, 42, 100, -100]
        
        def safe_divide(a, b):
            return Success(a / b) if b != 0 else Error("division by zero")
        
        def safe_sqrt(x):
            return Success(x ** 0.5) if x >= 0 else Error("negative sqrt")
        
        for value in test_values:
            # Test left identity: pure(a).bind(f) = f(a)
            f = lambda x: safe_divide(x, 2)
            left = pure(value).bind(f)
            right = f(value)
            
            assert left.is_success() == right.is_success()
            if left.is_success():
                assert abs(left.unwrap() - right.unwrap()) < 1e-10
            else:
                assert left.error() == right.error()
            
            # Test right identity: m.bind(pure) = m
            m = Success(value)
            identity_result = m.bind(pure)
            assert identity_result.is_success()
            assert identity_result.unwrap() == value
    
    def test_monoid_properties_comprehensive(self):
        """Test monoid properties across different dictionary structures"""
        monoid = DictMonoid()
        empty = monoid.empty()
        
        test_dicts = [
            {},
            {"a": 1},
            {"a": 1, "b": 2},
            {"nested": {"x": 1, "y": 2}},
            {"mixed": [1, 2, 3], "nested": {"deep": {"deeper": "value"}}}
        ]
        
        for dict_a in test_dicts:
            # Left identity: empty ⊕ a = a
            left_result = monoid.combine(empty, dict_a)
            assert left_result == dict_a
            
            # Right identity: a ⊕ empty = a  
            right_result = monoid.combine(dict_a, empty)
            assert right_result == dict_a
            
            for dict_b in test_dicts:
                for dict_c in test_dicts:
                    # Associativity: (a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
                    left_assoc = monoid.combine(monoid.combine(dict_a, dict_b), dict_c)
                    right_assoc = monoid.combine(dict_a, monoid.combine(dict_b, dict_c))
                    assert left_assoc == right_assoc


if __name__ == "__main__":
    pytest.main([__file__, "-v"])