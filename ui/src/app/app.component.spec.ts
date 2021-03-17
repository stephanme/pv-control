import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { ReactiveFormsModule } from '@angular/forms';

import { MatToolbarModule } from '@angular/material/toolbar';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { HarnessLoader } from '@angular/cdk/testing';
import { TestbedHarnessEnvironment } from '@angular/cdk/testing/testbed';
import { MatButtonHarness } from '@angular/material/button/testing';
import { MatSlideToggleHarness } from '@angular/material/slide-toggle/testing';

import { AppComponent } from './app.component';
import { PvControl } from './pv-control.service';


describe('AppComponent', () => {
  let loader: HarnessLoader;
  let httpMock: HttpTestingController;
  let component: AppComponent;
  let fixture: ComponentFixture<AppComponent>;
  let pvControlData: PvControl;
  let onePhaseSelector: MatSlideToggleHarness;
  let refreshButton: MatButtonHarness;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        BrowserAnimationsModule,
        HttpClientTestingModule,
        ReactiveFormsModule,
        MatToolbarModule,
        MatCardModule,
        MatFormFieldModule,
        MatInputModule,
        MatIconModule,
        MatButtonModule,
        MatSlideToggleModule,
      ],
      declarations: [
        AppComponent
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AppComponent);
    loader = TestbedHarnessEnvironment.loader(fixture);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);

    pvControlData = {
      phases: 3
    };

    onePhaseSelector = await loader.getHarness(MatSlideToggleHarness.with({selector: '#onePhaseSelector'}));
    refreshButton = await loader.getHarness(MatButtonHarness.with({selector: '#refresh'}));
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should render the app', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.formGroup.get('phases')?.value).toBe(3);
    expect(component.formGroup.get('onePhaseSelector')?.value).toBe(false);
    expect(await onePhaseSelector.isChecked()).toBeFalse();
  });

  it('should refresh data', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.formGroup.get('phases')?.value).toBe(3);
    expect(component.formGroup.get('onePhaseSelector')?.value).toBe(false);

    pvControlData.phases = 1;
    await refreshButton.click();
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.formGroup.get('phases')?.value).toBe(1);
    expect(component.formGroup.get('onePhaseSelector')?.value).toBe(true);
    expect(await onePhaseSelector.isChecked()).toBeTrue();
  });

  it('should allow to switch to one phase charging', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.formGroup.get('phases')?.value).toBe(3);
    await onePhaseSelector.toggle();

    const req = httpMock.expectOne('./api/pvcontrol/phases');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toBe(1);
    req.flush(null);

    pvControlData.phases = 1;
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.formGroup.get('phases')?.value).toBe(1);
    expect(component.formGroup.get('onePhaseSelector')?.value).toBe(true);
    expect(await onePhaseSelector.isChecked()).toBeTrue();
  });
});
