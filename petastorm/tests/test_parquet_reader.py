#  Copyright (c) 2017-2018 Uber Technologies, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import itertools

import numpy as np
import pytest

from petastorm import make_batch_reader
# pylint: disable=unnecessary-lambda
from petastorm.tests.test_common import create_test_scalar_dataset


_D = [lambda url, **kwargs: make_batch_reader(url, reader_pool_type='dummy', **kwargs)]

# pylint: disable=unnecessary-lambda
_TP = [
    lambda url, **kwargs: make_batch_reader(url, reader_pool_type='thread', **kwargs),
    lambda url, **kwargs: make_batch_reader(url, reader_pool_type='process', **kwargs),
]


def _check_simple_reader(reader, expected_data):
    # Read a bunch of entries from the dataset and compare the data to reference
    expected_field_names = expected_data[0].keys()
    count = 0
    for row in reader:
        actual = row._asdict()

        # Compare value of each entry in the batch
        for i, id_value in enumerate(actual['id']):
            expected = next(d for d in expected_data if d['id'] == id_value)
            for field in expected_field_names:
                expected_value = expected[field]
                actual_value = actual[field][i, ...]
                np.testing.assert_equal(actual_value, expected_value)

        count += len(actual['id'])

    assert count == len(expected_data)


@pytest.mark.parametrize('reader_factory', _D + _TP)
def test_simple_read(scalar_dataset, reader_factory):
    """Just a bunch of read and compares of all values to the expected values using the different reader pools"""
    with reader_factory(scalar_dataset.url) as reader:
        _check_simple_reader(reader, scalar_dataset.data)


@pytest.mark.parametrize('reader_factory', _D)
def test_specify_columns_to_read(scalar_dataset, reader_factory):
    """Just a bunch of read and compares of all values to the expected values using the different reader pools"""
    with reader_factory(scalar_dataset.url, schema_fields=['id', 'float.*$']) as reader:
        sample = next(reader)
        assert set(sample._asdict().keys()) == {'id', 'float64'}
        assert sample.float64.size > 0


@pytest.mark.parametrize('reader_factory', _D)
def test_many_columns_non_petastorm_dataset(many_columns_non_petastorm_dataset, reader_factory):
    """Check if we can read a dataset with huge number of columns (1000 in this case)"""
    with reader_factory(many_columns_non_petastorm_dataset.url) as reader:
        sample = next(reader)
        assert set(sample._fields) == set(many_columns_non_petastorm_dataset.data[0].keys())


@pytest.mark.parametrize('reader_factory', _D)
@pytest.mark.parametrize('partition_by', [['string'], ['id'], ['string', 'id']])
def test_string_partition(reader_factory, tmpdir, partition_by):
    """Try datasets partitioned by a string, integer and string+integer fields"""
    url = 'file://' + tmpdir.strpath

    data = create_test_scalar_dataset(url, 10, partition_by=partition_by)
    with reader_factory(url) as reader:
        row_ids_batched = [row.id for row in reader]
    actual_row_ids = list(itertools.chain(*row_ids_batched))
    assert len(data) == len(actual_row_ids)


@pytest.mark.parametrize('reader_factory', _D)
def test_column_subset(scalar_dataset, reader_factory):
    """ Request subset of columns from reader, confirm that receive those columns and only those columns."""

    # Create field subset, by picking even-numbered fields from the available fields, counting from 0.
    # Since schema_fields is a list of regex patterns, not plain strings of field names, am keeping two
    # lists - one of decorated field_names to avoid undesired matches (i.e. getting "string" and "string2" when
    # request "string"), and one non-decorated to compare to returned fields.
    all_fields = sorted(scalar_dataset.data[0].keys())
    requested_fields = []
    requested_fields_as_regex = []
    for n in range(0, len(all_fields), 2):
        requested_fields.append(all_fields[n])
        requested_fields_as_regex.append("^" + all_fields[n] + "$")

    with reader_factory(scalar_dataset.url, schema_fields=requested_fields_as_regex) as reader:
        sample = next(reader)
        assert sorted(sample._asdict().keys()) == requested_fields


@pytest.mark.parametrize('reader_factory', _D)
def test_invalid_column_name(scalar_dataset, reader_factory):
    """ Request a column that doesn't exist, confirm that get exception."""

    # Grab first field from expected dataset, append random characters to it to get an invalid field name.
    all_fields = list(scalar_dataset.data[0].keys())
    bad_field = all_fields[0]
    while bad_field in all_fields:
        bad_field += "VR46"
    requested_fields = [bad_field]

    with pytest.raises(StopIteration):
        with reader_factory(scalar_dataset.url, schema_fields=requested_fields) as reader:
            # Have to do something with sample to avoid build error.
            sample = next(reader)
            assert sample
