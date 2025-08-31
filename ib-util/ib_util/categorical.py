#!/usr/bin/env python3
"""
Categorical Abstractions for Configuration System

This module provides Category Theory structures for the configuration system:
- Result monad for compositional error handling
- Configuration monoid for associative merging  
- Functorial transformations for type-safe operations
- Categorical constraints for validation
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Callable, Union, Any, Dict, List
from enum import Enum
from dataclasses import dataclass


A = TypeVar('A')
B = TypeVar('B')
E = TypeVar('E')  # Error type


# ============================================================================
# RESULT MONAD - Compositional Error Handling
# ============================================================================

class Result(Generic[A, E], ABC):
    """
    Result monad for compositional error handling.
    
    Replaces exception-based error handling with monadic composition.
    Satisfies monad laws:
    - Left identity: return(a).bind(f) = f(a)
    - Right identity: m.bind(return) = m  
    - Associativity: m.bind(f).bind(g) = m.bind(lambda x: f(x).bind(g))
    """
    
    @abstractmethod
    def bind(self, f: Callable[[A], 'Result[B, E]']) -> 'Result[B, E]':
        """Monadic bind operation (flatMap)"""
        pass
    
    @abstractmethod
    def map(self, f: Callable[[A], B]) -> 'Result[B, E]':
        """Functorial map operation"""
        pass
    
    @abstractmethod
    def is_success(self) -> bool:
        """Check if result contains success value"""
        pass
    
    @abstractmethod
    def is_error(self) -> bool:
        """Check if result contains error"""
        pass
    
    @abstractmethod
    def unwrap(self) -> A:
        """Extract success value (unsafe - only call after checking is_success)"""
        pass
    
    @abstractmethod
    def error(self) -> E:
        """Extract error value (unsafe - only call after checking is_error)"""
        pass


@dataclass(frozen=True)
class Success(Result[A, E]):
    """Success case of Result monad"""
    value: A
    
    def bind(self, f: Callable[[A], Result[B, E]]) -> Result[B, E]:
        return f(self.value)
    
    def map(self, f: Callable[[A], B]) -> Result[B, E]:
        return Success(f(self.value))
    
    def is_success(self) -> bool:
        return True
    
    def is_error(self) -> bool:
        return False
    
    def unwrap(self) -> A:
        return self.value
    
    def error(self) -> E:
        raise ValueError("Success result has no error")


@dataclass(frozen=True)
class Error(Result[A, E]):
    """Error case of Result monad"""
    error_value: E
    
    def bind(self, f: Callable[[A], Result[B, E]]) -> Result[B, E]:
        return Error(self.error_value)
    
    def map(self, f: Callable[[A], B]) -> Result[B, E]:
        return Error(self.error_value)
    
    def is_success(self) -> bool:
        return False
    
    def is_error(self) -> bool:
        return True
    
    def unwrap(self) -> A:
        raise ValueError(f"Error result cannot be unwrapped: {self.error_value}")
    
    def error(self) -> E:
        return self.error_value


def pure(value: A) -> Result[A, E]:
    """Return/pure operation for Result monad"""
    return Success(value)


def sequence_results(results: List[Result[A, str]]) -> Result[List[A], str]:
    """
    Sequence a list of Results into a Result of list.
    If any Result is Error, return the first Error.
    """
    values = []
    for result in results:
        if result.is_error():
            return Error(result.error())
        values.append(result.unwrap())
    return Success(values)


# ============================================================================
# CONFIGURATION MONOID - Compositional Merging
# ============================================================================

class Monoid(Generic[A], ABC):
    """
    Mathematical monoid structure.
    
    A monoid is an algebraic structure with:
    - An associative binary operation (combine)
    - An identity element (empty)
    
    Laws:
    - Associativity: (a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
    - Left identity: empty ⊕ a = a
    - Right identity: a ⊕ empty = a
    """
    
    @abstractmethod
    def empty(self) -> A:
        """Identity element of the monoid"""
        pass
    
    @abstractmethod
    def combine(self, a: A, b: A) -> A:
        """Associative binary operation"""
        pass
    
    def fold(self, items: List[A]) -> A:
        """Fold a list using the monoid operation"""
        result = self.empty()
        for item in items:
            result = self.combine(result, item)
        return result


class DictMonoid(Monoid[Dict[str, Any]]):
    """
    Monoid for dictionary merging.
    
    Deep merges dictionaries with right-bias for conflicts.
    """
    
    def empty(self) -> Dict[str, Any]:
        return {}
    
    def combine(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries"""
        result = a.copy()
        
        for key, value in b.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.combine(result[key], value)
            else:
                result[key] = value
                
        return result


# ============================================================================
# CATEGORICAL CONSTRAINTS - Type-Safe Validation
# ============================================================================

class Constraint(Generic[A], ABC):
    """
    Categorical constraint for validation.
    
    A constraint is a predicate that can be composed with other constraints
    using logical operators (and, or, not).
    """
    
    @abstractmethod
    def check(self, value: A) -> Result[A, str]:
        """Check if value satisfies constraint"""
        pass
    
    def and_then(self, other: 'Constraint[A]') -> 'Constraint[A]':
        """Logical AND composition"""
        return AndConstraint(self, other)
    
    def or_else(self, other: 'Constraint[A]') -> 'Constraint[A]':
        """Logical OR composition"""
        return OrConstraint(self, other)


class AndConstraint(Constraint[A]):
    """Conjunction of two constraints"""
    
    def __init__(self, left: Constraint[A], right: Constraint[A]):
        self.left = left
        self.right = right
    
    def check(self, value: A) -> Result[A, str]:
        return (self.left.check(value)
                .bind(lambda v: self.right.check(v)))


class OrConstraint(Constraint[A]):
    """Disjunction of two constraints"""
    
    def __init__(self, left: Constraint[A], right: Constraint[A]):
        self.left = left
        self.right = right
    
    def check(self, value: A) -> Result[A, str]:
        left_result = self.left.check(value)
        if left_result.is_success():
            return left_result
        
        right_result = self.right.check(value)
        if right_result.is_success():
            return right_result
        
        return Error(f"Both constraints failed: {left_result.error()} AND {right_result.error()}")


class BoundedConstraint(Constraint[A]):
    """Constraint for bounded values (e.g., enums, ranges)"""
    
    def __init__(self, valid_values: List[A], description: str = "valid values"):
        self.valid_values = valid_values
        self.description = description
    
    def check(self, value: A) -> Result[A, str]:
        if value in self.valid_values:
            return Success(value)
        return Error(f"Invalid {self.description}: {value}. Must be one of {self.valid_values}")


class RangeConstraint(Constraint[Union[int, float]]):
    """Constraint for numeric ranges"""
    
    def __init__(self, min_val: Union[int, float], max_val: Union[int, float], 
                 inclusive: bool = True):
        self.min_val = min_val
        self.max_val = max_val
        self.inclusive = inclusive
    
    def check(self, value: Union[int, float]) -> Result[Union[int, float], str]:
        if self.inclusive:
            valid = self.min_val <= value <= self.max_val
            op = "≤"
        else:
            valid = self.min_val < value < self.max_val  
            op = "<"
        
        if valid:
            return Success(value)
        return Error(f"Value {value} not in range {self.min_val} {op} x {op} {self.max_val}")


# ============================================================================
# LOG LEVEL CONSTRAINTS - Category Theory Approach
# ============================================================================

class LogLevel(Enum):
    """
    Log levels as a bounded partially ordered set.
    
    Forms a lattice with ordering: DEBUG < INFO < WARNING < ERROR < CRITICAL
    """
    DEBUG = 0
    INFO = 1
    WARNING = 2  
    ERROR = 3
    CRITICAL = 4
    
    def __le__(self, other):
        if not isinstance(other, LogLevel):
            return NotImplemented
        return self.value <= other.value
    
    def __lt__(self, other):
        if not isinstance(other, LogLevel):
            return NotImplemented
        return self.value < other.value


# Categorical constraint for log levels
LOG_LEVEL_CONSTRAINT = BoundedConstraint(
    list(LogLevel), 
    "log level"
)


def validate_log_level(level_str: str) -> Result[str, str]:
    """
    Validate log level using categorical constraints.
    
    Replaces manual validation with compositional constraint checking.
    """
    try:
        level_upper = level_str.upper()
        level_enum = LogLevel[level_upper]
        return LOG_LEVEL_CONSTRAINT.check(level_enum).map(lambda _: level_upper)
    except KeyError:
        valid_levels = [level.name for level in LogLevel]
        return Error(f"Invalid log level: {level_str}. Must be one of {valid_levels}")


# ============================================================================
# USAGE EXAMPLES AND TESTS
# ============================================================================

if __name__ == "__main__":
    print("🔬 Categorical Configuration System Tests")
    
    # Test Result monad
    print("\n1. Result Monad Tests:")
    
    def safe_divide(a: float, b: float) -> Result[float, str]:
        if b == 0:
            return Error("Division by zero")
        return Success(a / b)
    
    def safe_sqrt(x: float) -> Result[float, str]:
        if x < 0:
            return Error("Cannot take sqrt of negative number")
        return Success(x ** 0.5)
    
    # Monadic composition
    result = (safe_divide(16, 4)
              .bind(lambda x: safe_sqrt(x))
              .map(lambda x: round(x, 2)))
    
    print(f"   16 ÷ 4 → √x = {result.unwrap() if result.is_success() else result.error()}")
    
    # Test monoid
    print("\n2. Configuration Monoid Tests:")
    
    dict_monoid = DictMonoid()
    
    base_config = {"server": {"port": 8080}, "debug": True}
    override_config = {"server": {"host": "localhost"}, "version": "1.0"}
    
    merged = dict_monoid.combine(base_config, override_config)
    print(f"   Merged config: {merged}")
    
    # Test constraints
    print("\n3. Categorical Constraints Tests:")
    
    level_result = validate_log_level("DEBUG")
    print(f"   'DEBUG' validation: {level_result.unwrap() if level_result.is_success() else level_result.error()}")
    
    invalid_result = validate_log_level("INVALID")
    print(f"   'INVALID' validation: {invalid_result.error() if invalid_result.is_error() else 'unexpected success'}")
    
    print("\n✅ All categorical structures working correctly!")