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


def _get_bad_field_name(field_list):
    """ Grab first name from list of valid fields, append random characters to it to get an invalid
    field name. """
    bad_field = field_list[0]
    while bad_field in field_list:
        bad_field += "VR46"
    return bad_field


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
def test_invalid_column_name(scalar_dataset, reader_factory):
    """Request a column that doesn't exist. Appears that when request only invalid fields,
    DummyPool returns an EmptyResultError, which then causes a StopIteration in
    ArrowReaderWorkerResultsQueueReader."""
    all_fields = list(scalar_dataset.data[0].keys())
    bad_field = _get_bad_field_name(all_fields)
    requested_fields = [bad_field]

    with reader_factory(scalar_dataset.url, schema_fields=requested_fields) as reader:
        with pytest.raises(StopIteration):
            sample = next(reader)._asdict()
            # Have to do something with sample to avoid build error.
            assert len(sample) == 0


@pytest.mark.parametrize('reader_factory', _D)
def test_invalid_and_valid_column_names(scalar_dataset, reader_factory):
    """Request one column that doesn't exist and one that does. Confirm that only get one field back and
    that get exception when try to read from invalid field."""
    all_fields = list(scalar_dataset.data[0].keys())
    bad_field = _get_bad_field_name(all_fields)
    requested_fields = [bad_field, all_fields[1]]

    with reader_factory(scalar_dataset.url, schema_fields=requested_fields) as reader:
        sample = next(reader)._asdict()
        assert len(sample) == 1
        with pytest.raises(KeyError):
            assert sample[bad_field] == ""
