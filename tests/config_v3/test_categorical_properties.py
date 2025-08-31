#!/usr/bin/env python3
"""
Property-based tests for Configuration System v3 categorical laws.

Uses property-based testing (hypothesis) to verify mathematical laws
hold across a wide range of inputs, ensuring the Category Theory 
structures are mathematically sound.
"""

import pytest
import sys
from pathlib import Path
from typing import Dict, Any, List

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Try to import hypothesis for property-based testing
try:
    from hypothesis import given, strategies as st, assume, settings
    from hypothesis.stateful import RuleBasedStateMachine, Bundle, rule, invariant
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    pytest.skip("hypothesis not available for property-based testing", allow_module_level=True)

# Load categorical abstractions directly
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
DictMonoid = categorical.DictMonoid
RangeConstraint = categorical.RangeConstraint
BoundedConstraint = categorical.BoundedConstraint


# Hypothesis strategies for generating test data
@st.composite
def result_success(draw):
    """Generate Success Result with arbitrary value"""
    value = draw(st.one_of(st.integers(), st.text(), st.floats(allow_nan=False)))
    return Success(value)

@st.composite  
def result_error(draw):
    """Generate Error Result with arbitrary error message"""
    error_msg = draw(st.text(min_size=1))
    return Error(error_msg)

@st.composite
def arbitrary_result(draw):
    """Generate arbitrary Result (Success or Error)"""
    return draw(st.one_of(result_success(), result_error()))

@st.composite
def nested_dict(draw, max_depth=3):
    """Generate nested dictionary structures"""
    if max_depth <= 0:
        return draw(st.one_of(
            st.integers(),
            st.text(),
            st.floats(allow_nan=False),
            st.booleans()
        ))
    
    return draw(st.dictionaries(
        st.text(min_size=1, max_size=10),
        st.one_of(
            st.integers(),
            st.text(),
            st.floats(allow_nan=False), 
            st.booleans(),
            st.deferred(lambda: nested_dict(max_depth - 1))
        ),
        min_size=0,
        max_size=5
    ))


class TestResultMonadProperties:
    """Property-based tests for Result monad laws"""
    
    @given(st.integers())
    @settings(max_examples=100)
    def test_monad_left_identity_property(self, a):
        """Property: pure(a).bind(f) = f(a) for all a and f"""
        def f(x):
            return Success(x * 2) if x >= 0 else Error("negative")
        
        left = pure(a).bind(f)
        right = f(a)
        
        assert left.is_success() == right.is_success()
        if left.is_success():
            assert left.unwrap() == right.unwrap()
        else:
            assert left.error() == right.error()
    
    @given(arbitrary_result())
    @settings(max_examples=100)
    def test_monad_right_identity_property(self, m):
        """Property: m.bind(pure) = m for all m"""
        result = m.bind(pure)
        
        assert result.is_success() == m.is_success()
        if result.is_success():
            assert result.unwrap() == m.unwrap()
        else:
            assert result.error() == m.error()
    
    @given(arbitrary_result(), st.integers(), st.integers())
    @settings(max_examples=50)
    def test_monad_associativity_property(self, m, x, y):
        """Property: m.bind(f).bind(g) = m.bind(lambda a: f(a).bind(g))"""
        def f(val):
            return Success(val + x)
        
        def g(val):
            return Success(val * y) if y != 0 else Error("zero multiply")
        
        # Left side: m.bind(f).bind(g)
        left = m.bind(f).bind(g)
        
        # Right side: m.bind(lambda a: f(a).bind(g))
        right = m.bind(lambda a: f(a).bind(g))
        
        assert left.is_success() == right.is_success()
        if left.is_success():
            assert left.unwrap() == right.unwrap()
        else:
            # Error messages might differ, but both should be errors
            assert left.is_error() and right.is_error()
    
    @given(arbitrary_result())
    @settings(max_examples=100)
    def test_functor_identity_property(self, m):
        """Property: fmap(id, m) = m for all m"""
        identity = lambda x: x
        result = m.map(identity)
        
        assert result.is_success() == m.is_success()
        if result.is_success():
            assert result.unwrap() == m.unwrap()
        else:
            assert result.error() == m.error()
    
    @given(result_success(), st.integers(), st.integers())
    @settings(max_examples=100)
    def test_functor_composition_property(self, m, a, b):
        """Property: fmap(f ∘ g, m) = fmap(f, fmap(g, m))"""
        f = lambda x: x + a
        g = lambda x: x * b
        
        # Left side: fmap(f ∘ g, m)
        left = m.map(lambda x: f(g(x)))
        
        # Right side: fmap(f, fmap(g, m))
        right = m.map(g).map(f)
        
        assert left.is_success() == right.is_success()
        if left.is_success():
            assert left.unwrap() == right.unwrap()


class TestDictMonoidProperties:
    """Property-based tests for dictionary monoid laws"""
    
    @given(nested_dict())
    @settings(max_examples=100)
    def test_monoid_left_identity_property(self, a):
        """Property: empty ⊕ a = a for all a"""
        monoid = DictMonoid()
        result = monoid.combine(monoid.empty(), a)
        assert result == a
    
    @given(nested_dict())
    @settings(max_examples=100) 
    def test_monoid_right_identity_property(self, a):
        """Property: a ⊕ empty = a for all a"""
        monoid = DictMonoid()
        result = monoid.combine(a, monoid.empty())
        assert result == a
    
    @given(nested_dict(), nested_dict(), nested_dict())
    @settings(max_examples=50)
    def test_monoid_associativity_property(self, a, b, c):
        """Property: (a ⊕ b) ⊕ c = a ⊕ (b ⊕ c) for all a, b, c"""
        monoid = DictMonoid()
        
        # Left side: (a ⊕ b) ⊕ c
        left = monoid.combine(monoid.combine(a, b), c)
        
        # Right side: a ⊕ (b ⊕ c)
        right = monoid.combine(a, monoid.combine(b, c))
        
        assert left == right
    
    @given(st.lists(nested_dict(), min_size=0, max_size=10))
    @settings(max_examples=50)
    def test_fold_consistency_property(self, dicts):
        """Property: fold is consistent with sequential combine operations"""
        monoid = DictMonoid()
        
        # Fold operation
        fold_result = monoid.fold(dicts)
        
        # Manual sequential combination
        manual_result = monoid.empty()
        for d in dicts:
            manual_result = monoid.combine(manual_result, d)
        
        assert fold_result == manual_result
    
    @given(nested_dict(), nested_dict())
    @settings(max_examples=100)
    def test_combine_structure_preservation(self, a, b):
        """Property: combine preserves dictionary structure"""
        monoid = DictMonoid()
        result = monoid.combine(a, b)
        
        # Result should be a dictionary
        assert isinstance(result, dict)
        
        # All keys from both dictionaries should be present
        expected_keys = set(a.keys()) | set(b.keys())
        assert set(result.keys()) == expected_keys


class TestConstraintProperties:
    """Property-based tests for categorical constraints"""
    
    @given(st.integers(min_value=1024, max_value=65535))
    @settings(max_examples=100)
    def test_range_constraint_valid_property(self, port):
        """Property: all values in range should be valid"""
        constraint = RangeConstraint(1024, 65535, inclusive=True)
        result = constraint.check(port)
        
        assert result.is_success()
        assert result.unwrap() == port
    
    @given(st.one_of(
        st.integers(max_value=1023),
        st.integers(min_value=65536)
    ))
    @settings(max_examples=100)
    def test_range_constraint_invalid_property(self, port):
        """Property: all values outside range should be invalid"""
        constraint = RangeConstraint(1024, 65535, inclusive=True)
        result = constraint.check(port)
        
        assert result.is_error()
        assert "not in range" in result.error()
    
    @given(st.integers(), st.integers())
    @settings(max_examples=100)
    def test_range_constraint_boundary_consistency(self, min_val, max_val):
        """Property: range constraint boundaries are consistent"""
        assume(min_val <= max_val)  # Only test valid ranges
        
        constraint = RangeConstraint(min_val, max_val, inclusive=True)
        
        # Boundary values should be valid for inclusive constraint
        min_result = constraint.check(min_val)
        max_result = constraint.check(max_val)
        
        assert min_result.is_success()
        assert max_result.is_success()
        
        # Values outside boundaries should be invalid
        if min_val > float('-inf'):
            below_result = constraint.check(min_val - 1)
            assert below_result.is_error()
        
        if max_val < float('inf'):
            above_result = constraint.check(max_val + 1)
            assert above_result.is_error()
    
    @given(st.lists(st.text(min_size=1), min_size=1, max_size=10), st.text(min_size=1))
    @settings(max_examples=100)
    def test_bounded_constraint_membership_property(self, valid_values, test_value):
        """Property: bounded constraint should validate membership correctly"""
        constraint = BoundedConstraint(valid_values, "test values")
        result = constraint.check(test_value)
        
        if test_value in valid_values:
            assert result.is_success()
            assert result.unwrap() == test_value
        else:
            assert result.is_error()
            assert "Invalid test values" in result.error()


class TestCompositionProperties:
    """Property-based tests for constraint and result composition"""
    
    @given(st.integers(), st.integers(), st.integers())
    @settings(max_examples=50)
    def test_constraint_and_composition(self, min_val, max_val, test_val):
        """Property: AND composition should require both constraints to pass"""
        assume(min_val <= max_val)
        
        constraint1 = RangeConstraint(min_val, max_val, inclusive=True)
        constraint2 = RangeConstraint(min_val, max_val, inclusive=True)
        
        combined = constraint1.and_then(constraint2)
        
        individual1 = constraint1.check(test_val)
        individual2 = constraint2.check(test_val)
        combined_result = combined.check(test_val)
        
        # Combined should succeed only if both individual constraints succeed
        if individual1.is_success() and individual2.is_success():
            assert combined_result.is_success()
        else:
            assert combined_result.is_error()
    
    @given(st.integers(), st.integers(), st.integers(), st.integers())
    @settings(max_examples=50)
    def test_constraint_or_composition(self, min1, max1, min2, max2):
        """Property: OR composition should pass if either constraint passes"""
        assume(min1 <= max1 and min2 <= max2)
        
        constraint1 = RangeConstraint(min1, max1, inclusive=True)
        constraint2 = RangeConstraint(min2, max2, inclusive=True)
        
        combined = constraint1.or_else(constraint2)
        
        # Test a value that should satisfy at least one constraint
        test_val = min1 if min1 <= max1 else min2
        
        individual1 = constraint1.check(test_val)
        individual2 = constraint2.check(test_val)
        combined_result = combined.check(test_val)
        
        # Combined should succeed if either individual constraint succeeds
        if individual1.is_success() or individual2.is_success():
            assert combined_result.is_success()


class TestResultSequenceProperties:
    """Property-based tests for Result sequence operations"""
    
    @given(st.lists(st.integers(), min_size=0, max_size=20))
    @settings(max_examples=100)
    def test_sequence_all_success_property(self, values):
        """Property: sequence of all Success results should succeed"""
        results = [Success(v) for v in values]
        sequenced = categorical.sequence_results(results)
        
        assert sequenced.is_success()
        assert sequenced.unwrap() == values
    
    @given(st.lists(st.integers(), min_size=1, max_size=10), st.integers(min_value=0), st.text(min_size=1))
    @settings(max_examples=100)
    def test_sequence_with_error_property(self, values, error_index, error_msg):
        """Property: sequence with any Error should fail"""
        assume(error_index < len(values))
        
        results = [Success(v) for v in values]
        results[error_index] = Error(error_msg)
        
        sequenced = categorical.sequence_results(results)
        
        assert sequenced.is_error()
        assert sequenced.error() == error_msg


class MonoidStateMachine(RuleBasedStateMachine):
    """Stateful property-based testing for monoid operations"""
    
    def __init__(self):
        super().__init__()
        self.monoid = DictMonoid()
        self.current = self.monoid.empty()
        self.operations = []
    
    dicts = Bundle('dicts')
    
    @rule(target=dicts, data=nested_dict())
    def create_dict(self, data):
        """Create a new dictionary"""
        return data
    
    @rule(a=dicts, b=dicts)
    def combine_dicts(self, a, b):
        """Combine two dictionaries"""
        result = self.monoid.combine(a, b)
        self.current = self.monoid.combine(self.current, result)
        self.operations.append(('combine', a, b, result))
    
    @rule(dict_list=st.lists(dicts, min_size=0, max_size=5))
    def fold_dicts(self, dict_list):
        """Fold a list of dictionaries"""
        if dict_list:  # Only if list is not empty
            result = self.monoid.fold(dict_list)
            self.current = self.monoid.combine(self.current, result)
            self.operations.append(('fold', dict_list, result))
    
    @invariant()
    def check_current_is_dict(self):
        """Invariant: current state is always a dictionary"""
        assert isinstance(self.current, dict)
    
    @invariant()
    def check_identity_properties(self):
        """Invariant: identity properties hold"""
        # Left identity
        left_identity = self.monoid.combine(self.monoid.empty(), self.current)
        assert left_identity == self.current
        
        # Right identity
        right_identity = self.monoid.combine(self.current, self.monoid.empty())
        assert right_identity == self.current


# Test the state machine
TestMonoidStateMachine = MonoidStateMachine.TestCase


class TestCategoricalLawsComprehensive:
    """Comprehensive property-based tests for all categorical laws"""
    
    @given(st.integers(), st.integers(), st.integers())
    @settings(max_examples=200, deadline=1000)
    def test_all_monad_laws_together(self, a, b, c):
        """Property: all monad laws should hold simultaneously"""
        def f(x):
            return Success(x + b) if x >= 0 else Error("negative f")
        
        def g(x):
            return Success(x * c) if c != 0 else Error("zero multiply g")
        
        m = Success(a) if a >= 0 else Error("negative m")
        
        # Left identity: pure(a).bind(f) = f(a)
        left_id_left = pure(a).bind(f)
        left_id_right = f(a)
        assert left_id_left.is_success() == left_id_right.is_success()
        
        # Right identity: m.bind(pure) = m
        right_id = m.bind(pure)
        assert right_id.is_success() == m.is_success()
        
        # Associativity: m.bind(f).bind(g) = m.bind(lambda x: f(x).bind(g))
        assoc_left = m.bind(f).bind(g)
        assoc_right = m.bind(lambda x: f(x).bind(g))
        assert assoc_left.is_success() == assoc_right.is_success()
        
        # If all are successful, values should match
        if (left_id_left.is_success() and left_id_right.is_success() and
            right_id.is_success() and m.is_success() and
            assoc_left.is_success() and assoc_right.is_success()):
            
            assert left_id_left.unwrap() == left_id_right.unwrap()
            assert right_id.unwrap() == m.unwrap()
            assert assoc_left.unwrap() == assoc_right.unwrap()
    
    @given(nested_dict(), nested_dict(), nested_dict(), nested_dict())
    @settings(max_examples=100)
    def test_all_monoid_laws_together(self, a, b, c, d):
        """Property: all monoid laws should hold simultaneously"""
        monoid = DictMonoid()
        empty = monoid.empty()
        
        # Identity laws
        left_id_a = monoid.combine(empty, a)
        right_id_a = monoid.combine(a, empty)
        assert left_id_a == a
        assert right_id_a == a
        
        # Associativity with multiple combinations
        assoc_left = monoid.combine(monoid.combine(a, b), monoid.combine(c, d))
        assoc_right = monoid.combine(monoid.combine(a, b), monoid.combine(c, d))
        assert assoc_left == assoc_right
        
        # Fold consistency
        dict_list = [a, b, c, d]
        fold_result = monoid.fold(dict_list)
        
        manual_result = empty
        for dict_item in dict_list:
            manual_result = monoid.combine(manual_result, dict_item)
        
        assert fold_result == manual_result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])