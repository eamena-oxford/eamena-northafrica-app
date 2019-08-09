from django.test import TestCase
from arches.app.models.models import Concepts, EntityTypes


class TestE27Concepts(TestCase):

    def test_E27_name(self):
        ent = EntityTypes.objects.get(entitytypeid='HERITAGE_PLACE.E27')

        self.assertEqual(ent.entitytypeid, 'HERITAGE_PLACE.E27')
