from __future__ import unicode_literals

from django.db import models, transaction
from django.dispatch import Signal
from django.utils.timezone import now

from dj_cqrs.controller import producer
from dj_cqrs.constants import SignalType


post_bulk_create = Signal(providing_args=['instances'])
post_update = Signal(providing_args=['instances'])


class MasterSignals(object):
    """ Signals registry and handlers for CQRS master models. """
    @classmethod
    def register_model(cls, model_cls):
        """
        :param dj_cqrs.mixins.MasterMixin model_cls: Class inherited from CQRS MasterMixin.
        """
        models.signals.post_save.connect(cls.post_save, sender=model_cls)
        models.signals.post_delete.connect(cls.post_delete, sender=model_cls)

        post_bulk_create.connect(cls.post_bulk_create, sender=model_cls)
        post_update.connect(cls.post_bulk_update, sender=model_cls)

    @classmethod
    def post_save(cls, sender, **kwargs):
        """
        :param dj_cqrs.mixins.MasterMixin sender: Class or instance inherited from CQRS MasterMixin.
        """
        instance = kwargs['instance']
        instance_data = instance.to_cqrs_dict()
        signal_type = SignalType.SAVE
        producer_args = signal_type, sender.CQRS_ID, instance_data, instance.pk

        if cls._can_produce_cqrs_now(kwargs['using']):
            producer.produce(*producer_args)
        else:
            cls._produce_cqrs_when_possible(*producer_args)

    @classmethod
    def post_delete(cls, sender, **kwargs):
        """
        :param dj_cqrs.mixins.MasterMixin sender: Class or instance inherited from CQRS MasterMixin.
        """
        instance = kwargs['instance']
        instance_data = {
            'id': instance.pk, 'cqrs_revision': instance.cqrs_revision + 1, 'cqrs_updated': now(),
        }
        signal_type = SignalType.DELETE
        producer_args = signal_type, sender.CQRS_ID, instance_data, instance.pk

        # Delete is always in transaction!
        cls._produce_cqrs_when_possible(*producer_args)

    @classmethod
    def post_bulk_create(cls, sender, **kwargs):
        """
        :param dj_cqrs.mixins.MasterMixin sender: Class or instance inherited from CQRS MasterMixin.
        """
        for instance in kwargs['instances']:
            cls.post_save(sender, instance=instance, using=kwargs['using'])

    @classmethod
    def post_bulk_update(cls, sender, **kwargs):
        """
        :param dj_cqrs.mixins.MasterMixin sender: Class or instance inherited from CQRS MasterMixin.
        """
        for instance in kwargs['instances']:
            cls.post_save(sender, instance=instance, using=kwargs['using'])

    @staticmethod
    def _can_produce_cqrs_now(using):
        return not transaction.get_connection(using).in_atomic_block

    @staticmethod
    def _produce_cqrs_when_possible(*args):
        transaction.on_commit(lambda: producer.produce(*args))
